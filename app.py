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
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

print("=== DÉMARRAGE DE L'APPLICATION OPTIMISÉE ===")

@dataclass
class Building:
    name: str
    length: int
    width: int
    quantity: int
    culture_produced: float
    radius: int
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
    
    def get_min_boost_threshold(self) -> float:
        """Retourne le plus petit seuil de boost"""
        thresholds = []
        if self.boost_25 > 0:
            thresholds.append(self.boost_25)
        if self.boost_50 > 0:
            thresholds.append(self.boost_50)
        if self.boost_100 > 0:
            thresholds.append(self.boost_100)
        return min(thresholds) if thresholds else float('inf')

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.producer_positions = []  # (x, y, building, id, radius)
        self.consumer_positions = []  # (x, y, building, id) pour les boosts
        self.initialize_grids()
        
    def initialize_grids(self):
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.placement_grid[self.terrain_grid == 0] = -1
        
    def find_available_zones(self):
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
        if x + length > self.placement_grid.shape[0] or y + width > self.placement_grid.shape[1]:
            return False
            
        zone_set = set(zone)
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in zone_set:
                    return False
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        return True
    
    def calculate_culture_at_position(self, x: int, y: int, length: int, width: int) -> float:
        """Calcule la culture reçue à une position donnée"""
        total_culture = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        for px, py, p_building, p_id, p_radius in self.producer_positions:
            dist = abs(center_x - px) + abs(center_y - py)
            if dist <= p_radius:
                total_culture += p_building.culture_produced
        
        return total_culture
    
    def find_best_spot_for_consumer(self, consumer: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve le meilleur spot pour un consommateur (maximise la culture reçue)"""
        if not self.producer_positions:
            return None
            
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        best_score = -1
        best_placement = None
        best_culture = 0
        
        for orientation in ['H', 'V']:
            length, width = consumer.get_dimensions(orientation)
            
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        culture = self.calculate_culture_at_position(x, y, length, width)
                        
                        # Score basé sur la culture reçue
                        if culture > best_culture:
                            best_culture = culture
                            best_score = culture
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'culture': culture
                            }
        
        return best_placement
    
    def find_spot_near_producer(self, consumer: Building, zone: List[Tuple[int, int]], 
                               producer_x: int, producer_y: int, producer_radius: int) -> Optional[dict]:
        """Trouve un spot dans le rayon d'un producteur spécifique"""
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        best_dist = float('inf')
        best_placement = None
        
        for orientation in ['H', 'V']:
            length, width = consumer.get_dimensions(orientation)
            
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        center_x = x + length // 2
                        center_y = y + width // 2
                        dist = abs(center_x - producer_x) + abs(center_y - producer_y)
                        
                        if dist <= producer_radius and dist < best_dist:
                            best_dist = dist
                            culture = self.calculate_culture_at_position(x, y, length, width)
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'culture': culture, 'dist': dist
                            }
        
        return best_placement
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        length, width = building.get_dimensions(orientation)
        
        # Vérification finale
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer la culture reçue
        culture_recue = self.calculate_culture_at_position(x, y, length, width)
        
        if building.can_be_boosted():
            if culture_recue >= building.boost_100:
                boost = 2.0
                boost_level = "100%"
            elif culture_recue >= building.boost_50:
                boost = 1.5
                boost_level = "50%"
            elif culture_recue >= building.boost_25:
                boost = 1.25
                boost_level = "25%"
            else:
                boost = 1.0
                boost_level = "0%"
        else:
            boost = 1.0
            boost_level = "-"
        
        placed_info = {
            'building': building,
            'x': x, 'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id,
            'culture_recue': culture_recue,
            'boost': boost,
            'boost_level': boost_level
        }
        self.placed_buildings.append(placed_info)
        
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id, building.radius))
        else:
            center_x = x + length // 2
            center_y = y + width // 2
            self.consumer_positions.append((center_x, center_y, building, building_id))
        
        return True
    
    def place_all_buildings(self) -> dict:
        self.initialize_grids()
        self.placed_buildings = []
        self.producer_positions = []
        self.consumer_positions = []
        
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
        
        # Trier les producteurs par rayon (les plus grands d'abord)
        producers.sort(key=lambda b: -b.radius)
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        consumers.sort(key=lambda b: b.get_min_boost_threshold())
        
        # Identifier les zones
        self.find_available_zones()
        
        # PHASE 1: Placer les producteurs stratégiquement
        st.info("📌 Phase 1: Placement des producteurs...")
        self.available_zones.sort(key=len, reverse=True)
        
        # Placer les producteurs dans différentes zones pour couvrir tout le terrain
        for i, producer in enumerate(producers[:]):
            if not self.available_zones:
                break
            
            # Prendre une zone (tourniquet pour répartir)
            zone_idx = i % len(self.available_zones)
            zone = self.available_zones[zone_idx]
            
            xs = [p[0] for p in zone]
            ys = [p[1] for p in zone]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Essayer différentes positions
                for dx in [-3, -2, -1, 0, 1, 2, 3]:
                    for dy in [-3, -2, -1, 0, 1, 2, 3]:
                        x = max(min_x, min(center_x + dx, max_x - length + 1))
                        y = max(min_y, min(center_y + dy, max_y - width + 1))
                        
                        if self.can_place_in_zone(zone, x, y, length, width):
                            if self.place_building(producer, x, y, orientation):
                                producers.remove(producer)
                                placed = True
                                break
                    if placed:
                        break
                if placed:
                    break
            
            if placed:
                # Mettre à jour la zone
                new_zone = []
                for (zx, zy) in zone:
                    if self.placement_grid[zx, zy] == 0:
                        new_zone.append((zx, zy))
                
                if new_zone:
                    self.available_zones[zone_idx] = new_zone
                else:
                    self.available_zones.pop(zone_idx)
        
        # PHASE 2: Placer les consommateurs dans les rayons des producteurs
        st.info("📌 Phase 2: Placement des consommateurs dans les rayons...")
        
        consumers_placed_in_radius = 0
        consumers_with_boost = 0
        
        # Pour chaque consommateur, trouver le meilleur spot dans un rayon
        for consumer in consumers[:]:
            best_placement = None
            best_culture = -1
            best_zone_idx = -1
            
            # Chercher dans toutes les zones
            for zone_idx, zone in enumerate(self.available_zones):
                placement = self.find_best_spot_for_consumer(consumer, zone)
                if placement and placement['culture'] > best_culture:
                    best_culture = placement['culture']
                    best_placement = placement
                    best_zone_idx = zone_idx
            
            if best_placement:
                if self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                     best_placement['orientation']):
                    consumers.remove(consumer)
                    consumers_placed_in_radius += 1
                    if best_placement['culture'] > 0:
                        consumers_with_boost += 1
                    
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
        
        st.info(f"✅ {consumers_placed_in_radius} consommateurs placés dans des rayons")
        st.info(f"✅ {consumers_with_boost} consommateurs avec boost > 0")
        
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
                                    if self.place_building(building, x, y, orientation):
                                        placed = True
                                        break
        
        # Statistiques finales
        total_culture_produced = sum(p['building'].culture_produced for p in self.placed_buildings if p['building'].is_producer())
        
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
        
        cultures_recues = [p['culture_recue'] for p in self.placed_buildings if p['building'].can_be_boosted()]
        culture_moyenne = sum(cultures_recues) / len(cultures_recues) if cultures_recues else 0
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
            'remaining': len(remaining)
        }

def create_visual_excel_sheet(writer, grid: np.ndarray, placed_buildings: List[dict]):
    """Crée un onglet Excel avec une visualisation couleur des bâtiments"""
    
    # Créer un DataFrame pour la visualisation
    viz_data = []
    for i in range(grid.shape[0]):
        row = []
        for j in range(grid.shape[1]):
            val = grid[i, j]
            if val == -1:
                row.append("█")  # Case obstruée
            elif val == 0:
                row.append("·")  # Case libre
            else:
                # Trouver le bâtiment correspondant
                building = next((p for p in placed_buildings if p['building_id'] == val), None)
                if building:
                    # Mettre le nom abrégé (3 premières lettres)
                    row.append(building['building'].name[:3])
                else:
                    row.append(str(val))
        viz_data.append(row)
    
    df_viz = pd.DataFrame(viz_data)
    df_viz.to_excel(writer, sheet_name='Carte_couleurs', index=False, header=False)
    
    # Accéder à la feuille Excel pour ajouter des couleurs
    workbook = writer.book
    worksheet = writer.sheets['Carte_couleurs']
    
    # Palette de couleurs
    colors = [
        'FF6B6B', '4ECDC4', '45B7D1', '96CEB4', 'FFEEAD', 'D4A5A5',
        '9B59B6', '3498DB', 'E67E22', '2ECC71', 'E74C3C', '1ABC9C',
        'F1C40F', 'E67E22', '9B59B6', '34495E', '16A085', '27AE60',
        '2980B9', '8E44AD', 'F39C12', 'D35400', 'C0392B', 'BDC3C7'
    ]
    
    # Créer un mapping building_id -> couleur
    building_colors = {}
    for i, placed in enumerate(placed_buildings):
        building_id = placed['building_id']
        building_colors[building_id] = colors[i % len(colors)]
    
    # Appliquer les couleurs
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            cell = worksheet.cell(row=i+1, column=j+1)
            val = grid[i, j]
            
            if val == -1:
                cell.fill = PatternFill(start_color='404040', end_color='404040', fill_type='solid')
                cell.font = Font(color='FFFFFF', size=8)
                cell.alignment = Alignment(horizontal='center', vertical='center')
            elif val == 0:
                cell.fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
                cell.font = Font(color='000000', size=8)
                cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                # Couleur selon le bâtiment
                color = building_colors.get(val, 'CCCCCC')
                cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
                cell.font = Font(color='000000', size=8, bold=True)
                cell.alignment = Alignment(horizontal='center', vertical='center')
            
            # Ajuster la largeur des colonnes
            worksheet.column_dimensions[get_column_letter(j+1)].width = 3

def create_building_summary(placed_buildings: List[dict]) -> pd.DataFrame:
    """Crée un résumé de TOUS les bâtiments placés"""
    summary = []
    for p in placed_buildings:
        summary.append({
            'ID': p['building_id'],
            'Bâtiment': p['building'].name,
            'Type': '🏭 Producteur' if p['building'].is_producer() else '🏠 Consommateur',
            'X': p['x'],
            'Y': p['y'],
            'Orient': p['orientation'],
            'Dimensions': f"{p['length']}x{p['width']}",
            'Culture prod': p['building'].culture_produced if p['building'].is_producer() else 0,
            'Culture reçue': f"{p['culture_recue']:.0f}" if p['building'].can_be_boosted() else '-',
            'Boost': p['boost_level'],
            'Rayon': p['building'].radius if p['building'].is_producer() else '-'
        })
    return pd.DataFrame(summary)

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments - Version Boost Optimisée")
st.markdown("""
**Objectif :** Maximiser les boosts en plaçant les consommateurs dans les rayons des producteurs

**Stratégie :**
1. **Phase 1** : Placement stratégique des producteurs dans différentes zones
2. **Phase 2** : Placement des consommateurs dans les rayons pour maximiser la culture reçue
3. **Phase 3** : Placement du reste
""")

with st.sidebar:
    st.header("📁 Chargement")
    uploaded_file = st.file_uploader("Fichier Excel", type=['xlsx', 'xls'])
    optimize_button = st.button("🚀 Lancer l'optimisation boostée", type="primary")

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
        st.subheader("⚡ Distribution des boosts")
        boost_stats = results['boost_stats']
        
        cols = st.columns(4)
        colors = ['gold', 'lightgreen', 'lightblue', 'lightgray']
        for i, (label, count) in enumerate(boost_stats.items()):
            with cols[i]:
                st.markdown(f"""
                <div style='background-color: {colors[i]}; padding: 10px; border-radius: 5px; text-align: center'>
                    <h3 style='margin:0'>{label}</h3>
                    <h2 style='margin:0'>{count}</h2>
                </div>
                """, unsafe_allow_html=True)
        
        # Visualisation dans Streamlit
        st.subheader("🗺️ Carte de placement (dans l'application)")
        
        # Créer une matrice de couleurs pour l'affichage
        fig = go.Figure(data=go.Heatmap(
            z=results['grid'],
            colorscale='Viridis',
            showscale=False,
            text=results['grid'],
            texttemplate="%{text}",
            textfont={"size": 6}
        ))
        fig.update_layout(height=600, yaxis=dict(autorange='reversed'))
        st.plotly_chart(fig, use_container_width=True)
        
        # Tableau récapitulatif
        st.subheader("📋 Liste de tous les bâtiments placés")
        df_summary = create_building_summary(results['placed_buildings'])
        st.dataframe(df_summary, use_container_width=True)
        
        # Export avec visualisation Excel
        st.subheader("📥 Export Excel avec visualisation couleur")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Onglet avec tous les bâtiments
            df_summary.to_excel(writer, sheet_name='Tous_les_batiments', index=False)
            
            # Onglet avec visualisation couleur
            create_visual_excel_sheet(writer, results['grid'], results['placed_buildings'])
            
            # Onglet avec statistiques
            stats = {
                'Total bâtiments': results['total_buildings'],
                'Producteurs placés': results['producers_placed'],
                'Consommateurs placés': results['consumers_placed'],
                'Culture produite': results['total_culture_produced'],
                'Consommateurs dans rayon': results['consumers_with_culture'],
                'Culture moyenne reçue': f"{results['culture_moyenne_recue']:.0f}",
                'Boost 100%': boost_stats['100%'],
                'Boost 50%': boost_stats['50%'],
                'Boost 25%': boost_stats['25%'],
                'Sans boost': boost_stats['0%'],
                'Bâtiments non placés': total_demande - results['total_buildings']
            }
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
        
        st.download_button(
            label="📥 Télécharger le fichier Excel avec visualisation",
            data=output.getvalue(),
            file_name="placement_optimise_boosts.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)