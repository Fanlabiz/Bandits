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
    radius: int  # Rayon de propagation (en cases)
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
    
    def get_area(self) -> int:
        return self.length * self.width

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.producer_positions = []  # (x, y, building, id, rayon)
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
    
    def calculate_culture_in_radius(self, x: int, y: int, length: int, width: int, 
                                   radius: int) -> Tuple[float, List[str]]:
        """Calcule la culture reçue des producteurs dans le rayon donné"""
        total_culture = 0
        sources = []
        center_x = x + length // 2
        center_y = y + width // 2
        
        for px, py, p_building, p_id, p_radius in self.producer_positions:
            # Calculer la distance de Manhattan (plus rapide et adaptée à une grille)
            dist = abs(center_x - px) + abs(center_y - py)
            if dist <= radius:
                total_culture += p_building.culture_produced
                sources.append(p_building.name)
        
        return total_culture, sources
    
    def find_spot_in_radius(self, building: Building, zone: List[Tuple[int, int]], 
                           target_producer: Tuple) -> Optional[dict]:
        """
        Trouve un spot pour un consommateur dans le rayon d'un producteur spécifique
        """
        px, py, p_building, p_id, p_radius = target_producer
        
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        best_score = -1
        best_placement = None
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        # Vérifier si le centre est dans le rayon
                        center_x = x + length // 2
                        center_y = y + width // 2
                        dist = abs(center_x - px) + abs(center_y - py)
                        
                        if dist <= p_radius:
                            # Calculer la culture totale reçue (de tous les producteurs)
                            culture, sources = self.calculate_culture_in_radius(x, y, length, width, 
                                                                               building.radius)
                            
                            # Score basé sur la culture reçue
                            score = culture
                            
                            # Bonus pour être proche du producteur
                            score += (p_radius - dist) * 10
                            
                            if score > best_score:
                                best_score = score
                                best_placement = {
                                    'x': x, 'y': y, 'orientation': orientation,
                                    'culture': culture, 'sources': sources,
                                    'dist_to_producer': dist
                                }
        
        return best_placement
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        """Place un bâtiment et enregistre ses informations"""
        length, width = building.get_dimensions(orientation)
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer la culture reçue
        culture_recue, sources = self.calculate_culture_in_radius(x, y, length, width, 
                                                                  building.radius if building.can_be_boosted() else 0)
        
        # Calculer le boost
        if building.can_be_boosted():
            if culture_recue >= building.boost_100:
                boost = 2.0
            elif culture_recue >= building.boost_50:
                boost = 1.5
            elif culture_recue >= building.boost_25:
                boost = 1.25
            else:
                boost = 1.0
        else:
            boost = 1.0
        
        placed_info = {
            'building': building,
            'x': x, 'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id,
            'culture_recue': culture_recue,
            'sources': sources,
            'boost': boost
        }
        self.placed_buildings.append(placed_info)
        
        # Si c'est un producteur, ajouter à la liste des positions
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id, building.radius))
        
        return True
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments en maximisant les boosts"""
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
        
        st.info(f"🎯 {len(producers)} producteurs (rayons: {[p.radius for p in producers]}), {len(consumers)} consommateurs")
        
        # Trier les producteurs par rayon (les plus grands d'abord)
        producers.sort(key=lambda b: -b.radius)
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        consumers.sort(key=lambda b: (b.boost_25 if b.boost_25 > 0 else 99999))
        
        # Identifier les zones
        self.find_available_zones()
        initial_free = np.sum(self.placement_grid == 0)
        
        # PHASE 1: Placer les producteurs au centre des zones
        st.info("📌 Phase 1: Placement des producteurs...")
        self.available_zones.sort(key=len, reverse=True)
        
        for producer in producers[:]:
            if not self.available_zones:
                break
                
            zone = self.available_zones[0]
            
            xs = [p[0] for p in zone]
            ys = [p[1] for p in zone]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
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
                
                self.available_zones.sort(key=len, reverse=True)
        
        # PHASE 2: Pour chaque producteur, placer des consommateurs dans son rayon
        st.info("📌 Phase 2: Placement des consommateurs autour des producteurs...")
        
        consumers_placed_in_radius = 0
        consumers_to_place = consumers.copy()
        
        # Pour chaque producteur
        for producer_idx, (px, py, p_building, p_id, p_radius) in enumerate(self.producer_positions):
            if not consumers:
                break
                
            st.info(f"   Producteur {p_building.name} (rayon {p_radius})")
            
            # Chercher des consommateurs à placer dans son rayon
            for consumer in consumers[:]:
                if not consumers:
                    break
                    
                best_placement = None
                best_culture = -1
                best_zone_idx = -1
                
                # Chercher dans toutes les zones disponibles
                for zone_idx, zone in enumerate(self.available_zones):
                    placement = self.find_spot_in_radius(consumer, zone, (px, py, p_building, p_id, p_radius))
                    if placement and placement['culture'] > best_culture:
                        best_culture = placement['culture']
                        best_placement = placement
                        best_zone_idx = zone_idx
                
                if best_placement:
                    self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                      best_placement['orientation'])
                    consumers.remove(consumer)
                    consumers_placed_in_radius += 1
                    
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
        
        st.info(f"✅ {consumers_placed_in_radius} consommateurs placés dans un rayon")
        
        # PHASE 3: Placer le reste
        remaining = producers + consumers
        if remaining:
            st.info(f"📌 Phase 3: Placement des {len(remaining)} bâtiments restants...")
            
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
        
        # Nombre de consommateurs avec culture > 0
        consumers_with_culture = sum(1 for p in self.placed_buildings if p['building'].can_be_boosted() and p['culture_recue'] > 0)
        total_consumers = sum(1 for p in self.placed_buildings if p['building'].can_be_boosted())
        
        return {
            'total_buildings': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'total_culture_produced': total_culture_produced,
            'culture_moyenne_recue': culture_moyenne,
            'consumers_with_culture': consumers_with_culture,
            'total_consumers': total_consumers,
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'producers_placed': len([p for p in self.placed_buildings if p['building'].is_producer()]),
            'consumers_placed': total_consumers,
            'initial_free': initial_free,
            'occupied': np.sum(self.placement_grid > 0),
            'free': np.sum(self.placement_grid == 0),
            'obstructed': np.sum(self.placement_grid == -1)
        }

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments")
st.markdown("""
**Objectif :** Maximiser la culture reçue par les bâtiments

**Stratégie :**
1. Les **producteurs** (avec culture > 0) sont placés au centre
2. Les **consommateurs** sont placés dans leur rayon (2-4 cases)
3. On optimise la proximité pour maximiser la culture reçue
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
        
        # Compter producteurs et consommateurs
        n_producers = sum(b.quantity for b in buildings if b.is_producer())
        n_consumers = sum(b.quantity for b in buildings if b.can_be_boosted())
        
        st.success(f"✅ {len(buildings)} types, {total_demande} bâtiments")
        st.info(f"🗺️ Terrain: {cells_libres} cases libres")
        st.info(f"🎯 {n_producers} producteurs, {n_consumers} consommateurs")
        
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
            st.metric("📊 Dans un rayon", f"{results['consumers_with_culture']}/{results['total_consumers']}")
        with col4:
            st.metric("🎯 Culture moyenne", f"{results['culture_moyenne_recue']:.0f}")
        
        # Statistiques des boosts
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
        
        # Tableau des placements
        st.subheader("📋 Détail des placements (culture reçue)")
        
        placement_data = []
        for p in results['placed_buildings']:
            if p['building'].can_be_boosted():
                seuils = f"{p['building'].boost_25:.0f}/{p['building'].boost_50:.0f}/{p['building'].boost_100:.0f}"
                
                # Déterminer le niveau de boost
                if p['culture_recue'] >= p['building'].boost_100:
                    boost_level = "100%"
                elif p['culture_recue'] >= p['building'].boost_50:
                    boost_level = "50%"
                elif p['culture_recue'] >= p['building'].boost_25:
                    boost_level = "25%"
                else:
                    boost_level = "0%"
                
                placement_data.append({
                    'Bâtiment': p['building'].name,
                    'Culture reçue': f"{p['culture_recue']:.0f}",
                    'Boost': boost_level,
                    'Seuils': seuils,
                    'Sources': ', '.join(p['sources']) if p['sources'] else '-'
                })
        
        # Trier par culture reçue
        placement_data.sort(key=lambda x: float(x['Culture reçue']) if x['Culture reçue'] != '0' else -1, reverse=True)
        
        df_placements = pd.DataFrame(placement_data)
        st.dataframe(df_placements, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_placements.to_excel(writer, sheet_name='Placements', index=False)
            pd.DataFrame(results['grid']).to_excel(writer, sheet_name='Grille', index=False, header=False)
            
            stats = {
                'Placés': results['total_buildings'],
                'Total': total_demande,
                'Culture produite': results['total_culture_produced'],
                'Dans rayon': results['consumers_with_culture'],
                'Total consommateurs': results['total_consumers']
            }
            stats.update(results['boost_stats'])
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
        
        st.download_button("📥 Télécharger les résultats", data=output.getvalue(), 
                          file_name="resultats_rayons_reels.xlsx")
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)