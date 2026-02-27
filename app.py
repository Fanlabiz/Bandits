"""Application Streamlit pour placement de bâtiments - Regroupement optimal"""
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
import math
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from collections import defaultdict

print("=== DÉMARRAGE DE L'APPLICATION REGROUPEMENT OPTIMAL ===")

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
    
    def get_area(self) -> int:
        return self.length * self.width
    
    def get_boost_potential(self) -> float:
        """Potentiel de boost (culture produite / seuil moyen)"""
        if not self.can_be_boosted():
            return 0
        seuil_moyen = (self.boost_25 + self.boost_50 + self.boost_100) / 3
        return 100 / seuil_moyen if seuil_moyen > 0 else 0

class Zone:
    """Représente une zone contiguë de cases libres"""
    def __init__(self, cells: List[Tuple[int, int]]):
        self.cells = set(cells)
        self.cells_list = cells
        self.size = len(cells)
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        self.min_x = min(xs)
        self.max_x = max(xs)
        self.min_y = min(ys)
        self.max_y = max(ys)
        self.width = self.max_y - self.min_y + 1
        self.height = self.max_x - self.min_x + 1
        
    def can_place(self, x: int, y: int, length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé"""
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in self.cells:
                    return False
        return True
    
    def place_building(self, x: int, y: int, length: int, width: int):
        """Retire les cases utilisées par un bâtiment"""
        for i in range(length):
            for j in range(width):
                self.cells.discard((x + i, y + j))
        # Mettre à jour les listes
        self.cells_list = list(self.cells)
        self.size = len(self.cells)
        if self.cells:
            xs = [c[0] for c in self.cells]
            ys = [c[1] for c in self.cells]
            self.min_x = min(xs)
            self.max_x = max(xs)
            self.min_y = min(ys)
            self.max_y = max(ys)
        else:
            self.min_x = self.max_x = self.min_y = self.max_y = 0

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.zones: List[Zone] = []
        self.producer_positions = []  # (x, y, building, id, radius)
        self.initialize_grids()
        
    def initialize_grids(self):
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.placement_grid[self.terrain_grid == 0] = -1
        
    def find_zones(self):
        """Identifie toutes les zones de cases libres contiguës"""
        visited = np.zeros_like(self.placement_grid, dtype=bool)
        self.zones = []
        
        for i in range(self.placement_grid.shape[0]):
            for j in range(self.placement_grid.shape[1]):
                if self.placement_grid[i, j] == 0 and not visited[i, j]:
                    cells = []
                    stack = [(i, j)]
                    visited[i, j] = True
                    
                    while stack:
                        x, y = stack.pop()
                        cells.append((x, y))
                        for dx, dy in [(0,1), (1,0), (0,-1), (-1,0)]:
                            nx, ny = x+dx, y+dy
                            if (0 <= nx < self.placement_grid.shape[0] and 
                                0 <= ny < self.placement_grid.shape[1] and
                                self.placement_grid[nx, ny] == 0 and 
                                not visited[nx, ny]):
                                visited[nx, ny] = True
                                stack.append((nx, ny))
                    
                    if cells:
                        self.zones.append(Zone(cells))
        
        # Trier les zones par taille (grandes d'abord)
        self.zones.sort(key=lambda z: -z.size)
        return len(self.zones)
    
    def calculate_culture_at_position(self, x: int, y: int, length: int, width: int) -> float:
        """Calcule la culture reçue par un CONSOMMATEUR à une position"""
        total_culture = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        for px, py, p_building, p_id, p_radius in self.producer_positions:
            dist = abs(center_x - px) + abs(center_y - py)
            if dist <= p_radius:
                total_culture += p_building.culture_produced
        
        return total_culture
    
    def find_best_spot_for_consumer(self, consumer: Building, zone: Zone) -> Optional[dict]:
        """Trouve le meilleur spot pour un consommateur (maximise la culture reçue)"""
        if not self.producer_positions:
            return None
            
        best_score = -1
        best_placement = None
        best_culture = -1
        
        for orientation in ['H', 'V']:
            length, width = consumer.get_dimensions(orientation)
            
            for x in range(zone.min_x, zone.max_x - length + 2):
                for y in range(zone.min_y, zone.max_y - width + 2):
                    if zone.can_place(x, y, length, width):
                        culture = self.calculate_culture_at_position(x, y, length, width)
                        
                        # Score = culture reçue (plus c'est haut, mieux c'est)
                        if culture > best_culture:
                            best_culture = culture
                            best_score = culture
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'culture': culture
                            }
        
        return best_placement
    
    def find_all_spots(self, building: Building, zone: Zone) -> List[dict]:
        """Trouve TOUS les spots disponibles pour un bâtiment"""
        spots = []
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            for x in range(zone.min_x, zone.max_x - length + 2):
                for y in range(zone.min_y, zone.max_y - width + 2):
                    if zone.can_place(x, y, length, width):
                        spots.append({
                            'x': x, 'y': y, 'orientation': orientation
                        })
        return spots
    
    def place_building(self, building: Building, x: int, y: int, orientation: str, zone: Zone) -> bool:
        """Place un bâtiment dans une zone"""
        length, width = building.get_dimensions(orientation)
        
        # Vérification
        if not zone.can_place(x, y, length, width):
            return False
        
        building_id = len(self.placed_buildings) + 1
        
        # Placer dans la grille
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Retirer de la zone
        zone.place_building(x, y, length, width)
        
        # Calculer la culture reçue
        culture_recue = 0
        if building.can_be_boosted():
            culture_recue = self.calculate_culture_at_position(x, y, length, width)
        
        # Déterminer le boost
        boost_level = "-"
        if building.can_be_boosted():
            if culture_recue >= building.boost_100:
                boost_level = "🔥 100%"
            elif culture_recue >= building.boost_50:
                boost_level = "✨ 50%"
            elif culture_recue >= building.boost_25:
                boost_level = "⭐ 25%"
            else:
                boost_level = "⚪ 0%"
        
        placed_info = {
            'building': building,
            'x': x, 'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id,
            'culture_recue': culture_recue if building.can_be_boosted() else 0,
            'boost_level': boost_level
        }
        self.placed_buildings.append(placed_info)
        
        # Ajouter aux producteurs si nécessaire
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id, building.radius))
        
        return True
    
    def place_all_buildings(self) -> dict:
        """Place TOUS les bâtiments avec regroupement optimal"""
        self.initialize_grids()
        self.placed_buildings = []
        self.producer_positions = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Compter les quantités
        producer_counts = defaultdict(int)
        consumer_counts = defaultdict(int)
        all_producers = []
        all_consumers = []
        
        for building in self.buildings:
            for _ in range(building.quantity):
                if building.is_producer():
                    all_producers.append(building)
                    producer_counts[building.name] += 1
                elif building.can_be_boosted():
                    all_consumers.append(building)
                    consumer_counts[building.name] += 1
        
        st.info(f"🎯 {len(all_producers)} producteurs, {len(all_consumers)} consommateurs")
        
        # Trier les producteurs par rayon (les plus grands d'abord)
        all_producers.sort(key=lambda b: (-b.radius, -b.culture_produced))
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        all_consumers.sort(key=lambda b: b.get_boost_potential(), reverse=True)
        
        # Identifier les zones
        self.find_zones()
        st.info(f"🗺️ {len(self.zones)} zones identifiées")
        
        # PHASE 1: Créer des clusters producteurs + consommateurs
        st.info("📌 Phase 1: Création de clusters de boost...")
        
        clusters_formed = 0
        consumers_in_clusters = 0
        
        # On va créer des clusters autour des meilleurs producteurs
        for producer in all_producers[:]:
            if not self.zones:
                break
                
            # Prendre la plus grande zone
            zone = self.zones[0]
            
            # Chercher un emplacement pour le producteur
            producer_placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Essayer au centre de la zone
                center_x = (zone.min_x + zone.max_x) // 2
                center_y = (zone.min_y + zone.max_y) // 2
                
                for dx in range(-5, 6):
                    for dy in range(-5, 6):
                        x = max(zone.min_x, min(center_x + dx, zone.max_x - length + 1))
                        y = max(zone.min_y, min(center_y + dy, zone.max_y - width + 1))
                        
                        if zone.can_place(x, y, length, width):
                            if self.place_building(producer, x, y, orientation, zone):
                                all_producers.remove(producer)
                                producer_placed = True
                                clusters_formed += 1
                                break
                    if producer_placed:
                        break
                if producer_placed:
                    break
            
            if producer_placed:
                # Maintenant, placer des consommateurs dans le rayon de ce producteur
                px, py = producer_placed_x, producer_placed_y = (x + length//2, y + width//2)
                p_radius = producer.radius
                
                # Chercher des consommateurs compatibles
                for consumer in all_consumers[:]:
                    if not zone.cells:
                        break
                    
                    # Chercher un spot dans le rayon
                    best_spot = None
                    best_culture = -1
                    
                    for orientation in ['H', 'V']:
                        c_len, c_wid = consumer.get_dimensions(orientation)
                        
                        for cx in range(max(zone.min_x, px - p_radius - c_len), 
                                       min(zone.max_x - c_len + 1, px + p_radius + 1)):
                            for cy in range(max(zone.min_y, py - p_radius - c_wid), 
                                           min(zone.max_y - c_wid + 1, py + p_radius + 1)):
                                if zone.can_place(cx, cy, c_len, c_wid):
                                    # Vérifier si dans le rayon
                                    dist = abs(cx + c_len//2 - px) + abs(cy + c_wid//2 - py)
                                    if dist <= p_radius:
                                        culture = self.calculate_culture_at_position(cx, cy, c_len, c_wid)
                                        if culture > best_culture:
                                            best_culture = culture
                                            best_spot = (cx, cy, orientation)
                    
                    if best_spot and best_culture > 0:
                        cx, cy, corient = best_spot
                        if self.place_building(consumer, cx, cy, corient, zone):
                            all_consumers.remove(consumer)
                            consumers_in_clusters += 1
                
                # Mettre à jour la liste des zones (la zone a changé)
                self.zones = [z for z in self.zones if z.cells]
                self.zones.sort(key=lambda z: -z.size)
        
        st.info(f"✅ {clusters_formed} clusters formés, {consumers_in_clusters} consommateurs dans des rayons")
        
        # PHASE 2: Placer les producteurs restants
        st.info("📌 Phase 2: Placement des producteurs restants...")
        
        for producer in all_producers[:]:
            if not self.zones:
                break
            
            # Prendre la plus grande zone
            zone = self.zones[0]
            
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Essayer au centre
                center_x = (zone.min_x + zone.max_x) // 2
                center_y = (zone.min_y + zone.max_y) // 2
                
                for dx in range(-3, 4):
                    for dy in range(-3, 4):
                        x = max(zone.min_x, min(center_x + dx, zone.max_x - length + 1))
                        y = max(zone.min_y, min(center_y + dy, zone.max_y - width + 1))
                        
                        if zone.can_place(x, y, length, width):
                            if self.place_building(producer, x, y, orientation, zone):
                                all_producers.remove(producer)
                                placed = True
                                break
                    if placed:
                        break
                if placed:
                    break
            
            if placed:
                self.zones = [z for z in self.zones if z.cells]
                self.zones.sort(key=lambda z: -z.size)
        
        # PHASE 3: Placer les consommateurs restants (priorité à ceux dans les rayons)
        st.info("📌 Phase 3: Placement des consommateurs restants...")
        
        consumers_in_radius_phase2 = 0
        for consumer in all_consumers[:]:
            if not self.zones:
                break
            
            best_zone = None
            best_spot = None
            best_culture = -1
            
            for zone in self.zones:
                spot = self.find_best_spot_for_consumer(consumer, zone)
                if spot and spot['culture'] > best_culture:
                    best_culture = spot['culture']
                    best_spot = spot
                    best_zone = zone
            
            if best_spot:
                if self.place_building(consumer, best_spot['x'], best_spot['y'], 
                                     best_spot['orientation'], best_zone):
                    all_consumers.remove(consumer)
                    if best_culture > 0:
                        consumers_in_radius_phase2 += 1
                    
                    self.zones = [z for z in self.zones if z.cells]
                    self.zones.sort(key=lambda z: -z.size)
        
        st.info(f"✅ {consumers_in_radius_phase2} consommateurs supplémentaires dans des rayons")
        
        # PHASE 4: Remplissage maximal de toutes les zones
        st.info("📌 Phase 4: Remplissage maximal...")
        
        remaining = all_producers + all_consumers
        
        # Trier par taille (petits d'abord) pour maximiser le nombre
        remaining.sort(key=lambda b: b.get_area())
        
        filled_count = 0
        for building in remaining[:]:
            if not self.zones:
                break
            
            placed = False
            for zone in self.zones:
                spots = self.find_all_spots(building, zone)
                if spots:
                    # Prendre le premier spot disponible
                    spot = spots[0]
                    if self.place_building(building, spot['x'], spot['y'], 
                                         spot['orientation'], zone):
                        remaining.remove(building)
                        filled_count += 1
                        placed = True
                        break
            
            if placed:
                self.zones = [z for z in self.zones if z.cells]
                self.zones.sort(key=lambda z: -z.size)
        
        st.info(f"✅ {filled_count} bâtiments placés en phase 4")
        
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
            'unplaced': len(remaining)
        }

def create_visual_excel_sheet(writer, grid: np.ndarray, placed_buildings: List[dict]):
    """Crée un onglet Excel avec visualisation couleur"""
    
    # Créer un mapping ID -> abréviation
    id_to_abbr = {}
    for p in placed_buildings:
        name = p['building'].name
        if p['building'].is_producer():
            # Producteur: 3 premières lettres en MAJ
            abbr = name[:3].upper()
        else:
            # Consommateur: 3 premières lettres en min
            abbr = name[:3].lower()
        id_to_abbr[p['building_id']] = abbr
    
    viz_data = []
    for i in range(grid.shape[0]):
        row = []
        for j in range(grid.shape[1]):
            val = grid[i, j]
            if val == -1:
                row.append("█")
            elif val == 0:
                row.append("·")
            else:
                row.append(id_to_abbr.get(val, "??"))
        viz_data.append(row)
    
    df_viz = pd.DataFrame(viz_data)
    df_viz.to_excel(writer, sheet_name='Carte', index=False, header=False)
    
    workbook = writer.book
    worksheet = writer.sheets['Carte']
    
    # Palette de couleurs
    colors = [
        'FF6B6B', '4ECDC4', '45B7D1', '96CEB4', 'FFEEAD', 'D4A5A5',
        '9B59B6', '3498DB', 'E67E22', '2ECC71', 'E74C3C', '1ABC9C',
        'F1C40F', 'E67E22', '9B59B6', '34495E', '16A085', '27AE60',
        '2980B9', '8E44AD', 'F39C12', 'D35400', 'C0392B', 'BDC3C7'
    ]
    
    building_colors = {}
    for i, placed in enumerate(placed_buildings):
        building_id = placed['building_id']
        building_colors[building_id] = colors[i % len(colors)]
    
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            cell = worksheet.cell(row=i+1, column=j+1)
            val = grid[i, j]
            
            if val == -1:
                cell.fill = PatternFill(start_color='404040', end_color='404040', fill_type='solid')
                cell.font = Font(color='FFFFFF', size=8)
            elif val == 0:
                cell.fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
                cell.font = Font(color='000000', size=8)
            else:
                color = building_colors.get(val, 'CCCCCC')
                cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
                cell.font = Font(color='000000', size=8, bold=True)
            
            cell.alignment = Alignment(horizontal='center', vertical='center')
            worksheet.column_dimensions[get_column_letter(j+1)].width = 3

def create_building_summary(placed_buildings: List[dict]) -> pd.DataFrame:
    """Crée un résumé des bâtiments placés"""
    summary = []
    for p in placed_buildings:
        if p['building'].can_be_boosted():
            seuils = f"{p['building'].boost_25:.0f}/{p['building'].boost_50:.0f}/{p['building'].boost_100:.0f}"
            culture_recue = f"{p['culture_recue']:.0f}"
        else:
            seuils = "-"
            culture_recue = "-"
        
        summary.append({
            'ID': p['building_id'],
            'Bâtiment': p['building'].name,
            'Type': '🏭 PROD' if p['building'].is_producer() else '🏠 CONS',
            'X': p['x'],
            'Y': p['y'],
            'Orient': p['orientation'],
            'Dimensions': f"{p['length']}x{p['width']}",
            'Culture prod': p['building'].culture_produced if p['building'].is_producer() else 0,
            'Culture reçue': culture_recue,
            'Boost': p['boost_level'],
            'Seuils': seuils,
            'Rayon': p['building'].radius if p['building'].is_producer() else '-'
        })
    return pd.DataFrame(summary)

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement - Regroupement Optimal")
st.markdown("""
**Stratégie en 4 phases :**
1. **Création de clusters** : Producteur + consommateurs dans son rayon
2. **Placement des producteurs** restants
3. **Placement des consommateurs** prioritaires dans les rayons
4. **Remplissage maximal** de l'espace restant
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
        
        # Visualisation
        st.subheader("🗺️ Carte de placement")
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
        
        # Tableau
        st.subheader("📋 Bâtiments placés")
        df_summary = create_building_summary(results['placed_buildings'])
        st.dataframe(df_summary, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='Batiments', index=False)
            create_visual_excel_sheet(writer, results['grid'], results['placed_buildings'])
            
            stats = {
                'Total bâtiments': results['total_buildings'],
                'Producteurs': results['producers_placed'],
                'Consommateurs': results['total_consumers'],
                'Culture produite': results['total_culture_produced'],
                'Culture moyenne': f"{results['culture_moyenne_recue']:.0f}",
                'Boost 100%': boost_stats['100%'],
                'Boost 50%': boost_stats['50%'],
                'Boost 25%': boost_stats['25%'],
                'Sans boost': boost_stats['0%'],
                'Non placés': total_demande - results['total_buildings']
            }
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Stats', index=False)
        
        st.download_button(
            label="📥 Télécharger Excel",
            data=output.getvalue(),
            file_name="placement_regroupe.xlsx"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)