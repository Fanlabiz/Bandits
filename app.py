"""Application Streamlit pour placement de bâtiments avec optimisation des boosts"""
import streamlit as st
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
import copy
import io
import plotly.graph_objects as go
import plotly.express as px
import sys
from collections import defaultdict
import math

print("=== DÉMARRAGE DE L'APPLICATION OPTIMISÉE ===")

@dataclass
class Building:
    """Classe représentant un bâtiment"""
    name: str
    length: int
    width: int
    quantity: int
    culture_produced: float  # Culture que ce bâtiment PRODUIT
    radius: int  # Rayon de propagation
    boost_25: float
    boost_50: float
    boost_100: float
    
    def get_dimensions(self, orientation: str) -> Tuple[int, int]:
        if orientation == 'H':
            return self.length, self.width
        else:
            return self.width, self.length
    
    def is_producer(self) -> bool:
        return self.culture_produced > 0 and self.radius > 0
    
    def can_be_boosted(self) -> bool:
        return (self.boost_25 > 0 or self.boost_50 > 0 or self.boost_100 > 0)
    
    def get_boost_ratio(self) -> float:
        """Retourne le ratio culture nécessaire / culture produite pour être boosté"""
        if not self.can_be_boosted():
            return float('inf')
        # Prendre le plus petit seuil comme indicateur
        min_threshold = min(t for t in [self.boost_25, self.boost_50, self.boost_100] if t > 0)
        return min_threshold

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.producer_positions = []  # Positions des producteurs déjà placés
        self.initialize_grids()
        
    def initialize_grids(self):
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.placement_grid[self.terrain_grid == 0] = -1
        
    def find_available_zones(self):
        """Trouve toutes les zones de cases libres"""
        visited = np.zeros_like(self.placement_grid, dtype=bool)
        self.available_zones = []
        
        for i in range(self.placement_grid.shape[0]):
            for j in range(self.placement_grid.shape[1]):
                if self.placement_grid[i, j] == 0 and not visited[i, j]:
                    zone = []
                    stack = [(i, j)]
                    visited[i, j] = True
                    
                    while stack:
                        x, y = stack.pop()
                        zone.append((x, y))
                        for dx, dy in [(0,1), (1,0), (0,-1), (-1,0)]:
                            nx, ny = x+dx, y+dy
                            if (0 <= nx < self.placement_grid.shape[0] and 
                                0 <= ny < self.placement_grid.shape[1] and
                                self.placement_grid[nx, ny] == 0 and 
                                not visited[nx, ny]):
                                visited[nx, ny] = True
                                stack.append((nx, ny))
                    
                    if zone:
                        self.available_zones.append(zone)
        
        return len(self.available_zones)
    
    def can_place_in_zone(self, zone: List[Tuple[int, int]], x: int, y: int, 
                          length: int, width: int) -> bool:
        zone_set = set(zone)
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in zone_set:
                    return False
        return True
    
    def calculate_culture_at_position(self, x: int, y: int, length: int, width: int, 
                                     radius: int) -> Tuple[float, List[str], List[Tuple[int, int]]]:
        """
        Calcule la culture reçue à une position ET retourne les sources
        """
        total_culture = 0
        sources = []
        source_positions = []
        center_x = x + length // 2
        center_y = y + width // 2
        
        # Chercher tous les producteurs dans le rayon
        for px, py, p_building, p_id in self.producer_positions:
            # Calculer la distance
            dist = math.sqrt((center_x - px)**2 + (center_y - py)**2)
            if dist <= radius:
                total_culture += p_building.culture_produced
                sources.append(p_building.name)
                source_positions.append((px, py))
        
        return total_culture, sources, source_positions
    
    def calculate_boost_for_building(self, building: Building, x: int, y: int, 
                                    length: int, width: int) -> Tuple[float, float, List[str]]:
        if not building.can_be_boosted():
            return 1.0, 0, []
        
        total_culture, sources, _ = self.calculate_culture_at_position(x, y, length, width, building.radius)
        
        if total_culture >= building.boost_100:
            return 2.0, total_culture, sources
        elif total_culture >= building.boost_50:
            return 1.5, total_culture, sources
        elif total_culture >= building.boost_25:
            return 1.25, total_culture, sources
        else:
            return 1.0, total_culture, sources
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        length, width = building.get_dimensions(orientation)
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer la culture reçue
        culture_recue, sources, _ = self.calculate_culture_at_position(x, y, length, width, 
                                                                       building.radius if building.can_be_boosted() else 0)
        
        placed_info = {
            'building': building,
            'x': x, 'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id,
            'culture_recue': culture_recue,
            'sources': sources
        }
        self.placed_buildings.append(placed_info)
        
        # Si c'est un producteur, ajouter à la liste des positions
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id))
        
        return True
    
    def find_best_spot_near_producers(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """
        Trouve le meilleur spot pour un consommateur en maximisant la culture reçue
        """
        if not self.producer_positions:
            return None
            
        best_score = -1
        best_placement = None
        
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        # Calculer la culture reçue à cette position
                        culture, sources, source_positions = self.calculate_culture_at_position(
                            x, y, length, width, building.radius
                        )
                        
                        # Score basé sur la culture reçue
                        score = culture
                        
                        # Bonus si proche des producteurs
                        center_x = x + length // 2
                        center_y = y + width // 2
                        for sx, sy in source_positions:
                            dist = math.sqrt((center_x - sx)**2 + (center_y - sy)**2)
                            score += (building.radius - dist) * 10  # Bonus de proximité
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'culture': culture, 'sources': sources
                            }
        
        return best_placement
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments en maximisant la culture reçue"""
        self.initialize_grids()
        self.placed_buildings = []
        self.producer_positions = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Séparer producteurs et consommateurs
        producers = []
        consumers = []
        for building in self.buildings:
            for _ in range(building.quantity):
                if building.is_producer():
                    producers.append(building)
                else:
                    consumers.append(building)
        
        st.info(f"🎯 {len(producers)} producteurs, {len(consumers)} consommateurs")
        
        # Trier les producteurs par culture produite
        producers.sort(key=lambda b: -b.culture_produced)
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        consumers.sort(key=lambda b: b.get_boost_ratio())
        
        # Identifier les zones
        self.find_available_zones()
        initial_free = np.sum(self.placement_grid == 0)
        
        # PHASE 1: Placer les GROS producteurs au centre des grandes zones
        self.available_zones.sort(key=len, reverse=True)
        
        for producer in producers[:]:
            if not self.available_zones:
                break
                
            # Prendre la plus grande zone
            zone = self.available_zones[0]
            
            # Calculer les limites de la zone
            xs = [p[0] for p in zone]
            ys = [p[1] for p in zone]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            # Centre de la zone
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            
            # Essayer les deux orientations
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Calculer la position optimale près du centre
                x = max(min_x, min(center_x - length//2, max_x - length + 1))
                y = max(min_y, min(center_y - width//2, max_y - width + 1))
                
                if self.can_place_in_zone(zone, x, y, length, width):
                    self.place_building(producer, x, y, orientation)
                    producers.remove(producer)
                    placed = True
                    break
            
            if placed:
                # Mettre à jour la zone
                new_zone = []
                for (zx, zy) in zone:
                    if self.placement_grid[zx, zy] == 0:
                        new_zone.append((zx, zy))
                
                if new_zone:
                    self.available_zones[0] = new_zone
                else:
                    self.available_zones.pop(0)
                
                # Retrier les zones
                self.available_zones.sort(key=len, reverse=True)
        
        # PHASE 2: Placer les consommateurs AUTOUR des producteurs
        # Recalculer les zones
        self.find_available_zones()
        
        # Pour chaque consommateur, trouver le meilleur spot près des producteurs
        consumers_to_place = consumers.copy()
        for consumer in consumers_to_place:
            best_placement = None
            best_culture = -1
            best_zone_idx = -1
            
            for zone_idx, zone in enumerate(self.available_zones):
                placement = self.find_best_spot_near_producers(consumer, zone)
                if placement and placement['culture'] > best_culture:
                    best_culture = placement['culture']
                    best_placement = placement
                    best_zone_idx = zone_idx
            
            if best_placement:
                self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                  best_placement['orientation'])
                consumers.remove(consumer)
                
                # Mettre à jour la zone
                if best_zone_idx >= 0:
                    zone = self.available_zones[best_zone_idx]
                    new_zone = []
                    for (zx, zy) in zone:
                        if self.placement_grid[zx, zy] == 0:
                            new_zone.append((zx, zy))
                    
                    if new_zone:
                        self.available_zones[best_zone_idx] = new_zone
                    else:
                        self.available_zones.pop(best_zone_idx)
        
        # PHASE 3: Placer le reste
        remaining = producers + consumers
        for building in remaining:
            placed = False
            for zone_idx, zone in enumerate(self.available_zones):
                if placed:
                    break
                
                xs = [p[0] for p in zone]
                ys = [p[1] for p in zone]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                
                for orientation in ['H', 'V']:
                    if placed:
                        break
                    length, width = building.get_dimensions(orientation)
                    
                    if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                        continue
                    
                    for x in range(min_x, max_x - length + 2):
                        if placed:
                            break
                        for y in range(min_y, max_y - width + 2):
                            if self.can_place_in_zone(zone, x, y, length, width):
                                self.place_building(building, x, y, orientation)
                                placed = True
                                break
        
        # Calculer les statistiques finales
        total_culture_produced = sum(p['building'].culture_produced for p in self.placed_buildings if p['building'].is_producer())
        
        # Statistiques des boosts
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        for p in self.placed_buildings:
            if p['building'].can_be_boosted():
                if p['culture_recue'] >= p['building'].boost_100:
                    boost_stats['100%'] += 1
                elif p['culture_recue'] >= p['building'].boost_50:
                    boost_stats['50%'] += 1
                elif p['culture_recue'] >= p['building'].boost_25:
                    boost_stats['25%'] += 1
                else:
                    boost_stats['0%'] += 1
        
        # Culture moyenne reçue par les consommateurs
        cultures_recues = [p['culture_recue'] for p in self.placed_buildings if p['building'].can_be_boosted()]
        culture_moyenne = sum(cultures_recues) / len(cultures_recues) if cultures_recues else 0
        
        return {
            'total_buildings': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'total_culture_produced': total_culture_produced,
            'culture_moyenne_recue': culture_moyenne,
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'producers_placed': len([p for p in self.placed_buildings if p['building'].is_producer()]),
            'consumers_placed': len([p for p in self.placed_buildings if p['building'].can_be_boosted()]),
            'initial_free': initial_free,
            'occupied': np.sum(self.placement_grid > 0),
            'free': np.sum(self.placement_grid == 0),
            'obstructed': np.sum(self.placement_grid == -1)
        }

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments - Version Optimisée")
st.markdown("""
**Objectif :** Maximiser la culture reçue par chaque bâtiment

**Stratégie :**
1. Les **producteurs** (sites culturels) sont placés au centre des zones
2. Les **consommateurs** sont placés au plus près des producteurs
3. La **distance** est optimisée pour maximiser la culture reçue
""")

with st.sidebar:
    st.header("📁 Chargement")
    uploaded_file = st.file_uploader("Fichier Excel", type=['xlsx', 'xls'])
    optimize_button = st.button("🚀 Lancer l'optimisation", type="primary")

if uploaded_file and optimize_button:
    try:
        # Lecture
        df_terrain = pd.read_excel(uploaded_file, sheet_name=0, header=None, engine='openpyxl')
        df_buildings = pd.read_excel(uploaded_file, sheet_name=1, engine='openpyxl')
        
        terrain_grid = df_terrain.values.astype(int)
        
        # Création des bâtiments
        buildings = []
        for _, row in df_buildings.iterrows():
            def get_float(col, default=0):
                val = row[col] if col in row else default
                return float(val) if not pd.isna(val) else default
            
            def get_int(col, default=1):
                val = row[col] if col in row else default
                return int(val) if not pd.isna(val) else default
            
            building = Building(
                name=str(row['Nom']),
                length=get_int('longueur', 1),
                width=get_int('largeur', 1),
                quantity=get_int('quantité', 1),
                culture_produced=get_float('culture', 0),
                radius=get_int('rayonnement', 0),
                boost_25=get_float('Boost 25%', 0),
                boost_50=get_float('Boost 50%', 0),
                boost_100=get_float('Boost 100%', 0)
            )
            buildings.append(building)
        
        total_demande = sum(b.quantity for b in buildings)
        cells_libres = np.sum(terrain_grid == 1)
        
        st.success(f"✅ {len(buildings)} types, {total_demande} bâtiments")
        st.info(f"🗺️ Terrain: {cells_libres} cases libres")
        
        # Placement
        placer = BuildingPlacer(terrain_grid, buildings)
        results = placer.place_all_buildings()
        
        # Résultats
        st.subheader("📊 Résultats")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🏢 Placés", f"{results['total_buildings']}/{total_demande}")
        with col2:
            st.metric("💰 Culture produite", f"{results['total_culture_produced']:.0f}")
        with col3:
            util = results['occupied'] / cells_libres * 100 if cells_libres > 0 else 0
            st.metric("📊 Utilisation", f"{util:.1f}%")
        with col4:
            st.metric("🎯 Culture moyenne reçue", f"{results['culture_moyenne_recue']:.0f}")
        
        # Détail des boosts
        st.subheader("⚡ Statistiques des boosts")
        boost_stats = results['boost_stats']
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🔥 Boost 100%", boost_stats['100%'])
        with col2:
            st.metric("✨ Boost 50%", boost_stats['50%'])
        with col3:
            st.metric("⭐ Boost 25%", boost_stats['25%'])
        with col4:
            st.metric("⚪ Sans boost", boost_stats['0%'])
        
        # Tableau des placements avec culture reçue
        st.subheader("📋 Détail des placements")
        placement_data = []
        for p in results['placed_buildings']:
            if p['building'].can_be_boosted():
                seuils = f"{p['building'].boost_25}/{p['building'].boost_50}/{p['building'].boost_100}"
            else:
                seuils = "-"
            
            placement_data.append({
                'Bâtiment': p['building'].name,
                'Type': 'Producteur' if p['building'].is_producer() else 'Consommateur',
                'X': p['x'], 'Y': p['y'],
                'Culture reçue': f"{p['culture_recue']:.0f}",
                'Seuils': seuils,
                'Sources': ', '.join(p['sources']) if p['sources'] else '-'
            })
        
        df_placements = pd.DataFrame(placement_data)
        st.dataframe(df_placements, use_container_width=True)
        
        # Visualisation
        st.subheader("🗺️ Carte de placement")
        fig = go.Figure(data=go.Heatmap(
            z=results['grid'],
            colorscale='Viridis',
            text=results['grid'],
            texttemplate="%{text}",
            textfont={"size": 6}
        ))
        fig.update_layout(height=700)
        st.plotly_chart(fig, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_placements.to_excel(writer, sheet_name='Placements', index=False)
            pd.DataFrame(results['grid']).to_excel(writer, sheet_name='Grille', index=False, header=False)
            
            stats = {
                'Placés': results['total_buildings'],
                'Total': total_demande,
                'Culture produite': results['total_culture_produced'],
                'Culture moyenne reçue': results['culture_moyenne_recue']
            }
            stats.update(results['boost_stats'])
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
        
        st.download_button("📥 Télécharger les résultats", data=output.getvalue(), 
                          file_name="resultats_optimises.xlsx")
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)