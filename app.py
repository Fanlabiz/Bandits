"""Application Streamlit pour placement de bâtiments - Optimisation complète"""
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

print("=== DÉMARRAGE DE L'APPLICATION OPTIMISATION COMPLÈTE ===")

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
    
    def get_min_boost_threshold(self) -> float:
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
        self.initialize_grids()
        
    def initialize_grids(self):
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.placement_grid[self.terrain_grid == 0] = -1
        
    def find_available_zones(self):
        """Identifie toutes les zones de cases libres contiguës"""
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
    
    def can_place(self, x: int, y: int, length: int, width: int) -> bool:
        """Vérifie si on peut placer un bâtiment à une position"""
        if x + length > self.placement_grid.shape[0] or y + width > self.placement_grid.shape[1]:
            return False
        
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        return True
    
    def calculate_culture_for_consumer(self, x: int, y: int, length: int, width: int) -> float:
        """Calcule la culture reçue par un CONSOMMATEUR à une position"""
        total_culture = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        for px, py, p_building, p_id, p_radius in self.producer_positions:
            dist = abs(center_x - px) + abs(center_y - py)
            if dist <= p_radius:
                total_culture += p_building.culture_produced
        
        return total_culture
    
    def find_all_positions_for_building(self, building: Building, zone: List[Tuple[int, int]]) -> List[dict]:
        """Trouve TOUTES les positions possibles pour un bâtiment dans une zone"""
        positions = []
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
                    if self.can_place(x, y, length, width):
                        culture = 0
                        if building.can_be_boosted():
                            culture = self.calculate_culture_for_consumer(x, y, length, width)
                        
                        positions.append({
                            'x': x, 'y': y,
                            'orientation': orientation,
                            'culture': culture
                        })
        return positions
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        """Place un bâtiment et retourne True si succès"""
        length, width = building.get_dimensions(orientation)
        
        # Double vérification
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer la culture reçue (seulement pour les consommateurs)
        culture_recue = 0
        if building.can_be_boosted():
            culture_recue = self.calculate_culture_for_consumer(x, y, length, width)
        
        # Déterminer le niveau de boost pour les consommateurs
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
        
        # Ajouter aux positions des producteurs si c'en est un
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id, building.radius))
        
        return True
    
    def fill_zone_greedy(self, zone: List[Tuple[int, int]], buildings_to_place: List[Building]) -> List[Building]:
        """Remplit une zone avec le maximum de bâtiments possible"""
        if not zone or not buildings_to_place:
            return buildings_to_place
        
        # Trier par taille (petits d'abord) pour maximiser le nombre
        buildings_to_place.sort(key=lambda b: (b.get_area(), -b.culture_produced))
        
        remaining = buildings_to_place.copy()
        zone_cells = set(zone)
        
        while remaining and zone_cells:
            # Prendre le plus petit bâtiment disponible
            building = remaining[0]
            
            # Chercher une position
            placed = False
            for orientation in ['H', 'V']:
                length, width = building.get_dimensions(orientation)
                
                for x, y in zone_cells:
                    if x + length <= self.placement_grid.shape[0] and y + width <= self.placement_grid.shape[1]:
                        # Vérifier si toutes les cases sont libres
                        valid = True
                        cells_to_use = []
                        for i in range(length):
                            for j in range(width):
                                cell = (x + i, y + j)
                                if cell not in zone_cells:
                                    valid = False
                                    break
                                cells_to_use.append(cell)
                            if not valid:
                                break
                        
                        if valid:
                            if self.place_building(building, x, y, orientation):
                                placed = True
                                # Retirer les cases utilisées
                                for cell in cells_to_use:
                                    zone_cells.remove(cell)
                                remaining.pop(0)
                                break
                    if placed:
                        break
                if placed:
                    break
            
            if not placed:
                # Si on ne peut pas placer ce bâtiment, on passe au suivant
                remaining.pop(0)
        
        return remaining
    
    def place_all_buildings(self) -> dict:
        """Place TOUS les bâtiments en 4 phases"""
        self.initialize_grids()
        self.placed_buildings = []
        self.producer_positions = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Séparer producteurs et consommateurs
        all_producers = []
        all_consumers = []
        for building in self.buildings:
            for _ in range(building.quantity):
                if building.is_producer():
                    all_producers.append(building)
                else:
                    all_consumers.append(building)
        
        st.info(f"🎯 {len(all_producers)} producteurs, {len(all_consumers)} consommateurs")
        
        # PHASE 1: Placer les producteurs stratégiquement
        st.info("📌 Phase 1: Placement des producteurs...")
        self.find_available_zones()
        self.available_zones.sort(key=len, reverse=True)
        
        # Trier les producteurs par rayon (les plus grands d'abord)
        all_producers.sort(key=lambda b: -b.radius)
        
        producers_placed = []
        for producer in all_producers:
            if not self.available_zones:
                break
            
            # Prendre la plus grande zone
            zone = self.available_zones[0]
            
            # Trouver le centre de la zone
            xs = [p[0] for p in zone]
            ys = [p[1] for p in zone]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Essayer différentes positions autour du centre
                for dx in range(-5, 6):
                    for dy in range(-5, 6):
                        x = max(min_x, min(center_x + dx, max_x - length + 1))
                        y = max(min_y, min(center_y + dy, max_y - width + 1))
                        
                        if self.can_place(x, y, length, width):
                            if self.place_building(producer, x, y, orientation):
                                producers_placed.append(producer)
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
                    self.available_zones[0] = new_zone
                else:
                    self.available_zones.pop(0)
                
                self.available_zones.sort(key=len, reverse=True)
        
        st.info(f"✅ {len(producers_placed)} producteurs placés")
        
        # PHASE 2: Placer les consommateurs dans les rayons des producteurs
        st.info("📌 Phase 2: Placement des consommateurs dans les rayons...")
        
        # Recalculer les zones
        self.find_available_zones()
        
        consumers_in_radius = []
        remaining_consumers = all_consumers.copy()
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        remaining_consumers.sort(key=lambda b: b.get_min_boost_threshold())
        
        for consumer in remaining_consumers[:]:
            best_placement = None
            best_culture = -1
            best_zone_idx = -1
            
            for zone_idx, zone in enumerate(self.available_zones):
                positions = self.find_all_positions_for_building(consumer, zone)
                for pos in positions:
                    if pos['culture'] > best_culture:
                        best_culture = pos['culture']
                        best_placement = pos
                        best_zone_idx = zone_idx
            
            if best_placement and best_culture > 0:
                if self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                     best_placement['orientation']):
                    consumers_in_radius.append(consumer)
                    remaining_consumers.remove(consumer)
                    
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
        
        st.info(f"✅ {len(consumers_in_radius)} consommateurs placés dans des rayons")
        
        # PHASE 3: Placer le reste des consommateurs (même sans boost)
        st.info("📌 Phase 3: Placement des consommateurs restants...")
        
        consumers_placed_no_boost = []
        for consumer in remaining_consumers[:]:
            best_placement = None
            best_zone_idx = -1
            
            for zone_idx, zone in enumerate(self.available_zones):
                positions = self.find_all_positions_for_building(consumer, zone)
                if positions:
                    # Prendre la première position disponible
                    best_placement = positions[0]
                    best_zone_idx = zone_idx
                    break
            
            if best_placement:
                if self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                     best_placement['orientation']):
                    consumers_placed_no_boost.append(consumer)
                    remaining_consumers.remove(consumer)
                    
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
        
        st.info(f"✅ {len(consumers_placed_no_boost)} consommateurs placés sans boost")
        
        # PHASE 4: Remplissage maximal des zones restantes
        st.info("📌 Phase 4: Remplissage maximal des zones...")
        
        # Rassembler tous les bâtiments non placés
        unplaced = [p for p in all_producers if p not in producers_placed] + remaining_consumers
        
        # Remplir chaque zone avec le maximum de bâtiments possible
        total_filled = 0
        for zone in self.available_zones:
            unplaced = self.fill_zone_greedy(zone, unplaced)
            if unplaced:
                total_filled += 1
        
        st.info(f"✅ Remplissage terminé, {len(unplaced)} bâtiments non placés")
        
        # Calculer les statistiques
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
        
        return {
            'total_buildings': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'total_culture_produced': total_culture_produced,
            'culture_moyenne_recue': culture_moyenne,
            'consumers_with_culture': len(consumers_in_radius),
            'total_consumers': len([p for p in self.placed_buildings if p['building'].can_be_boosted()]),
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'producers_placed': len([p for p in self.placed_buildings if p['building'].is_producer()]),
            'unplaced_count': len(unplaced)
        }

def create_visual_excel_sheet(writer, grid: np.ndarray, placed_buildings: List[dict]):
    """Crée un onglet Excel avec visualisation couleur"""
    
    # Créer un mapping ID -> abréviation
    id_to_abbr = {}
    for p in placed_buildings:
        # Prendre les 3 premières lettres du nom
        name = p['building'].name
        if p['building'].is_producer():
            abbr = name[:3].upper()
        else:
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
    df_viz.to_excel(writer, sheet_name='Carte_couleurs', index=False, header=False)
    
    workbook = writer.book
    worksheet = writer.sheets['Carte_couleurs']
    
    # Palette de couleurs
    colors = [
        'FF6B6B', '4ECDC4', '45B7D1', '96CEB4', 'FFEEAD', 'D4A5A5',
        '9B59B6', '3498DB', 'E67E22', '2ECC71', 'E74C3C', '1ABC9C',
        'F1C40F', 'E67E22', '9B59B6', '34495E', '16A085', '27AE60'
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
    """Crée un résumé de TOUS les bâtiments placés"""
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
            'Type': 'Producteur' if p['building'].is_producer() else 'Consommateur',
            'X': p['x'],
            'Y': p['y'],
            'Orientation': p['orientation'],
            'Dimensions': f"{p['length']}x{p['width']}",
            'Culture produite': p['building'].culture_produced if p['building'].is_producer() else 0,
            'Culture reçue': culture_recue,
            'Boost': p['boost_level'],
            'Seuils': seuils,
            'Rayon': p['building'].radius if p['building'].is_producer() else '-'
        })
    return pd.DataFrame(summary)

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments - Version Finale")
st.markdown("""
**Optimisation en 4 phases :**
1. **Placement stratégique** des producteurs
2. **Placement prioritaire** des consommateurs dans les rayons
3. **Placement maximal** des consommateurs restants
4. **Remplissage complet** de toutes les zones
""")

with st.sidebar:
    st.header("📁 Chargement")
    uploaded_file = st.file_uploader("Fichier Excel", type=['xlsx', 'xls'])
    optimize_button = st.button("🚀 Lancer l'optimisation finale", type="primary")

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
        
        # Tableau récapitulatif
        st.subheader("📋 Liste de tous les bâtiments placés")
        df_summary = create_building_summary(results['placed_buildings'])
        st.dataframe(df_summary, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='Tous_les_batiments', index=False)
            create_visual_excel_sheet(writer, results['grid'], results['placed_buildings'])
            
            stats = {
                'Total bâtiments': results['total_buildings'],
                'Producteurs placés': results['producers_placed'],
                'Consommateurs placés': results['total_consumers'],
                'Culture produite': results['total_culture_produced'],
                'Culture moyenne reçue': f"{results['culture_moyenne_recue']:.0f}",
                'Boost 100%': boost_stats['100%'],
                'Boost 50%': boost_stats['50%'],
                'Boost 25%': boost_stats['25%'],
                'Sans boost': boost_stats['0%'],
                'Non placés': total_demande - results['total_buildings']
            }
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
        
        st.download_button(
            label="📥 Télécharger le fichier Excel",
            data=output.getvalue(),
            file_name="placement_final.xlsx"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)