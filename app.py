"""Application Streamlit pour placement de bâtiments - Algorithme glouton avancé"""
import streamlit as st
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional, Set, Dict
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
import heapq

print("=== DÉMARRAGE DE L'APPLICATION ALGORITHME AVANCÉ ===")

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
    
    def get_boost_priority(self) -> float:
        """Priorité pour être boosté (plus le seuil est bas, plus c'est facile)"""
        if not self.can_be_boosted():
            return 0
        seuil_min = min(t for t in [self.boost_25, self.boost_50, self.boost_100] if t > 0)
        return 1000 / seuil_min if seuil_min > 0 else 0

class Placement:
    """Représente un placement possible"""
    def __init__(self, x: int, y: int, orientation: str, building: Building):
        self.x = x
        self.y = y
        self.orientation = orientation
        self.building = building
        self.length, self.width = building.get_dimensions(orientation)
        self.cells = [(x + i, y + j) for i in range(self.length) for j in range(self.width)]
        self.score = 0
        self.boost_potential = 0
        
    def get_center(self) -> Tuple[int, int]:
        return (self.x + self.length // 2, self.y + self.width // 2)

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = np.zeros_like(terrain_grid)
        self.placement_grid[terrain_grid == 0] = -1  # Cases obstruées
        self.placed_buildings: List[Placement] = []
        self.producers: List[Placement] = []  # Producteurs placés
        
    def get_free_cells(self) -> Set[Tuple[int, int]]:
        """Retourne l'ensemble des cellules libres"""
        free = set()
        for i in range(self.placement_grid.shape[0]):
            for j in range(self.placement_grid.shape[1]):
                if self.placement_grid[i, j] == 0:
                    free.add((i, j))
        return free
    
    def can_place(self, placement: Placement) -> bool:
        """Vérifie si un placement est possible"""
        for (x, y) in placement.cells:
            if x < 0 or x >= self.placement_grid.shape[0] or y < 0 or y >= self.placement_grid.shape[1]:
                return False
            if self.placement_grid[x, y] != 0:
                return False
        return True
    
    def place(self, placement: Placement) -> bool:
        """Place un bâtiment"""
        if not self.can_place(placement):
            return False
        
        building_id = len(self.placed_buildings) + 1
        for (x, y) in placement.cells:
            self.placement_grid[x, y] = building_id
        
        self.placed_buildings.append(placement)
        
        if placement.building.is_producer():
            self.producers.append(placement)
        
        return True
    
    def calculate_boost_for_placement(self, placement: Placement) -> float:
        """Calcule la culture reçue à cet emplacement"""
        if not placement.building.can_be_boosted():
            return 0
        
        center_x, center_y = placement.get_center()
        total_culture = 0
        
        for prod in self.producers:
            prod_center_x, prod_center_y = prod.get_center()
            dist = abs(center_x - prod_center_x) + abs(center_y - prod_center_y)
            if dist <= prod.building.radius:
                total_culture += prod.building.culture_produced
        
        return total_culture
    
    def find_all_placements(self, building: Building, free_cells: Set[Tuple[int, int]]) -> List[Placement]:
        """Trouve tous les placements possibles pour un bâtiment"""
        placements = []
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            # Optimisation: ne chercher que dans les zones où il y a des cellules libres
            cells_list = list(free_cells)
            if not cells_list:
                continue
                
            xs = [c[0] for c in cells_list]
            ys = [c[1] for c in cells_list]
            min_x, max_x = max(0, min(xs) - length), min(self.placement_grid.shape[0] - length, max(xs))
            min_y, max_y = max(0, min(ys) - width), min(self.placement_grid.shape[1] - width, max(ys))
            
            for x in range(min_x, max_x + 1):
                for y in range(min_y, max_y + 1):
                    placement = Placement(x, y, orientation, building)
                    
                    # Vérifier rapidement si les cellules sont libres
                    valid = True
                    for (cx, cy) in placement.cells:
                        if (cx, cy) not in free_cells:
                            valid = False
                            break
                    
                    if valid:
                        # Calculer le boost potentiel
                        culture = self.calculate_boost_for_placement(placement)
                        placement.score = culture
                        
                        # Ajouter un bonus pour les producteurs (être central)
                        if building.is_producer():
                            # Bonus pour être entouré de cases libres (potentiel de placement futur)
                            free_neighbors = 0
                            for (cx, cy) in placement.cells:
                                for dx, dy in [(0,1),(1,0),(0,-1),(-1,0)]:
                                    nx, ny = cx+dx, cy+dy
                                    if (nx, ny) in free_cells:
                                        free_neighbors += 1
                            placement.score += free_neighbors * 10
                        
                        placements.append(placement)
        
        return placements
    
    def find_best_placement(self, building: Building, free_cells: Set[Tuple[int, int]], 
                           prioritize_boost: bool = True) -> Optional[Placement]:
        """Trouve le meilleur placement pour un bâtiment"""
        placements = self.find_all_placements(building, free_cells)
        
        if not placements:
            return None
        
        if prioritize_boost and building.can_be_boosted():
            # Maximiser le boost reçu
            placements.sort(key=lambda p: -p.score)
        else:
            # Maximiser l'utilisation de l'espace (petits bâtiments d'abord)
            placements.sort(key=lambda p: (p.building.get_area(), -p.score))
        
        return placements[0]
    
    def try_place_cluster(self, producer: Building, consumers: List[Building], 
                         free_cells: Set[Tuple[int, int]]) -> Tuple[bool, Set[Tuple[int, int]]]:
        """Tente de placer un producteur avec des consommateurs dans son rayon"""
        # Trouver un emplacement pour le producteur
        prod_placement = self.find_best_placement(producer, free_cells, prioritize_boost=False)
        if not prod_placement:
            return False, free_cells
        
        # Sauvegarder l'état
        old_grid = self.placement_grid.copy()
        old_placed = self.placed_buildings.copy()
        old_producers = self.producers.copy()
        
        # Placer le producteur
        if not self.place(prod_placement):
            return False, free_cells
        
        # Mettre à jour les cellules libres
        new_free = free_cells - set(prod_placement.cells)
        
        # Placer les consommateurs dans le rayon
        consumers_placed = []
        prod_center = prod_placement.get_center()
        
        for consumer in consumers[:]:  # Copie pour itération
            # Chercher un emplacement dans le rayon
            best_placement = None
            best_culture = -1
            
            for orientation in ['H', 'V']:
                length, width = consumer.get_dimensions(orientation)
                
                # Chercher dans le rayon
                for dx in range(-producer.radius, producer.radius + 1):
                    for dy in range(-producer.radius, producer.radius + 1):
                        cx = prod_center[0] + dx - length//2
                        cy = prod_center[1] + dy - width//2
                        
                        # Vérifier les limites
                        if cx < 0 or cx >= self.placement_grid.shape[0] - length + 1:
                            continue
                        if cy < 0 or cy >= self.placement_grid.shape[1] - width + 1:
                            continue
                        
                        # Vérifier la distance
                        dist = abs(cx + length//2 - prod_center[0]) + abs(cy + width//2 - prod_center[1])
                        if dist > producer.radius:
                            continue
                        
                        # Vérifier si toutes les cellules sont libres
                        valid = True
                        cells = []
                        for i in range(length):
                            for j in range(width):
                                cell = (cx + i, cy + j)
                                if cell not in new_free:
                                    valid = False
                                    break
                                cells.append(cell)
                            if not valid:
                                break
                        
                        if valid:
                            culture = self.calculate_boost_for_placement(
                                Placement(cx, cy, orientation, consumer)
                            )
                            if culture > best_culture:
                                best_culture = culture
                                best_placement = (cx, cy, orientation, cells)
            
            if best_placement:
                cx, cy, corient, cells = best_placement
                placement = Placement(cx, cy, corient, consumer)
                if self.place(placement):
                    consumers_placed.append(consumer)
                    for cell in cells:
                        new_free.remove(cell)
        
        return True, new_free
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments avec une approche gloutonne multi-phase"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.placement_grid[self.terrain_grid == 0] = -1
        self.placed_buildings = []
        self.producers = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Compter les bâtiments
        producers = []
        consumers = []
        for building in self.buildings:
            for _ in range(building.quantity):
                if building.is_producer():
                    producers.append(building)
                elif building.can_be_boosted():
                    consumers.append(building)
        
        st.info(f"🎯 {len(producers)} producteurs, {len(consumers)} consommateurs")
        
        # Trier les producteurs par rayon (les plus grands d'abord)
        producers.sort(key=lambda b: (-b.radius, -b.culture_produced))
        
        # Trier les consommateurs par seuil (les plus faciles à booster d'abord)
        consumers.sort(key=lambda b: -b.get_boost_priority())
        
        free_cells = self.get_free_cells()
        initial_free = len(free_cells)
        
        # PHASE 1: Créer des clusters producteurs + consommateurs
        st.info("📌 Phase 1: Création de clusters de boost...")
        
        clusters_formed = 0
        consumers_in_clusters = 0
        
        for producer in producers[:]:
            if not free_cells:
                break
            
            # Prendre quelques consommateurs pour ce cluster
            cluster_consumers = consumers[:min(5, len(consumers))]
            
            success, free_cells = self.try_place_cluster(producer, cluster_consumers, free_cells)
            if success:
                producers.remove(producer)
                for c in cluster_consumers[:]:
                    if c in consumers:
                        consumers.remove(c)
                        consumers_in_clusters += 1
                clusters_formed += 1
        
        st.info(f"✅ {clusters_formed} clusters formés, {consumers_in_clusters} consommateurs dans des rayons")
        
        # PHASE 2: Placer les producteurs restants
        st.info("📌 Phase 2: Placement des producteurs restants...")
        
        for producer in producers[:]:
            if not free_cells:
                break
            
            placement = self.find_best_placement(producer, free_cells, prioritize_boost=False)
            if placement:
                if self.place(placement):
                    producers.remove(producer)
                    for cell in placement.cells:
                        free_cells.remove(cell)
        
        # PHASE 3: Placer les consommateurs en priorisant les boosts
        st.info("📌 Phase 3: Placement des consommateurs avec boosts...")
        
        consumers_in_radius = 0
        for consumer in consumers[:]:
            if not free_cells:
                break
            
            placement = self.find_best_placement(consumer, free_cells, prioritize_boost=True)
            if placement:
                if self.place(placement):
                    consumers.remove(consumer)
                    if placement.score > 0:
                        consumers_in_radius += 1
                    for cell in placement.cells:
                        free_cells.remove(cell)
        
        st.info(f"✅ {consumers_in_radius} consommateurs dans des rayons")
        
        # PHASE 4: Placement des consommateurs restants (sans boost)
        st.info("📌 Phase 4: Placement des consommateurs restants...")
        
        consumers_placed_no_boost = 0
        for consumer in consumers[:]:
            if not free_cells:
                break
            
            placement = self.find_best_placement(consumer, free_cells, prioritize_boost=False)
            if placement:
                if self.place(placement):
                    consumers.remove(consumer)
                    consumers_placed_no_boost += 1
                    for cell in placement.cells:
                        free_cells.remove(cell)
        
        st.info(f"✅ {consumers_placed_no_boost} consommateurs placés sans boost")
        
        # PHASE 5: Remplissage avec les producteurs restants (si encore des places)
        remaining = producers + consumers
        remaining.sort(key=lambda b: b.get_area())  # Petits d'abord
        
        filled = 0
        for building in remaining[:]:
            if not free_cells:
                break
            
            placement = self.find_best_placement(building, free_cells, prioritize_boost=False)
            if placement:
                if self.place(placement):
                    remaining.remove(building)
                    filled += 1
                    for cell in placement.cells:
                        free_cells.remove(cell)
        
        # Calculer les statistiques finales
        total_culture_produced = sum(p.building.culture_produced for p in self.producers)
        
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        cultures_recues = []
        
        for p in self.placed_buildings:
            if p.building.can_be_boosted():
                culture = self.calculate_boost_for_placement(p)
                cultures_recues.append(culture)
                
                if culture >= p.building.boost_100:
                    boost_stats['100%'] += 1
                elif culture >= p.building.boost_50:
                    boost_stats['50%'] += 1
                elif culture >= p.building.boost_25:
                    boost_stats['25%'] += 1
                else:
                    boost_stats['0%'] += 1
        
        culture_moyenne = sum(cultures_recues) / len(cultures_recues) if cultures_recues else 0
        consumers_with_culture = sum(1 for c in cultures_recues if c > 0)
        total_consumers = len([p for p in self.placed_buildings if p.building.can_be_boosted()])
        
        return {
            'total_buildings': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'total_culture_produced': total_culture_produced,
            'culture_moyenne_recue': culture_moyenne,
            'consumers_with_culture': consumers_with_culture,
            'total_consumers': total_consumers,
            'grid': self.placement_grid.copy(),
            'placed_buildings': self.placed_buildings,
            'boost_stats': boost_stats,
            'producers_placed': len(self.producers),
            'free_cells_remaining': len(free_cells),
            'initial_free': initial_free
        }

def create_visual_excel_sheet(writer, grid: np.ndarray, placed_buildings: List[Placement]):
    """Crée un onglet Excel avec visualisation couleur"""
    
    # Créer un mapping ID -> abréviation
    id_to_abbr = {}
    for i, p in enumerate(placed_buildings, 1):
        name = p.building.name
        if p.building.is_producer():
            abbr = name[:3].upper()
        else:
            abbr = name[:3].lower()
        id_to_abbr[i] = abbr
    
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
    for i, p in enumerate(placed_buildings, 1):
        building_colors[i] = colors[(i-1) % len(colors)]
    
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

def create_building_summary(placed_buildings: List[Placement], placer: BuildingPlacer) -> pd.DataFrame:
    """Crée un résumé des bâtiments placés"""
    summary = []
    for i, p in enumerate(placed_buildings, 1):
        culture = placer.calculate_boost_for_placement(p) if p.building.can_be_boosted() else 0
        
        if p.building.can_be_boosted():
            seuils = f"{p.building.boost_25:.0f}/{p.building.boost_50:.0f}/{p.building.boost_100:.0f}"
            if culture >= p.building.boost_100:
                boost = "🔥 100%"
            elif culture >= p.building.boost_50:
                boost = "✨ 50%"
            elif culture >= p.building.boost_25:
                boost = "⭐ 25%"
            else:
                boost = "⚪ 0%"
        else:
            seuils = "-"
            boost = "-"
        
        summary.append({
            'ID': i,
            'Bâtiment': p.building.name,
            'Type': '🏭 PROD' if p.building.is_producer() else '🏠 CONS',
            'X': p.x,
            'Y': p.y,
            'Orient': p.orientation,
            'Dimensions': f"{p.length}x{p.width}",
            'Culture prod': p.building.culture_produced if p.building.is_producer() else 0,
            'Culture reçue': f"{culture:.0f}" if p.building.can_be_boosted() else '-',
            'Boost': boost,
            'Seuils': seuils,
            'Rayon': p.building.radius if p.building.is_producer() else '-'
        })
    return pd.DataFrame(summary)

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement - Algorithme Glouton Avancé")
st.markdown("""
**Algorithme en 5 phases :**
1. **Création de clusters** : Producteur + consommateurs dans son rayon
2. **Producteurs restants** : Placement stratégique
3. **Consommateurs prioritaires** : Ceux qui peuvent être boostés
4. **Consommateurs restants** : Sans boost
5. **Remplissage final** : Avec les petits bâtiments
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
        df_summary = create_building_summary(results['placed_buildings'], placer)
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
                'Cases libres restantes': results['free_cells_remaining'],
                'Non placés': total_demande - results['total_buildings']
            }
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Stats', index=False)
        
        st.download_button(
            label="📥 Télécharger Excel",
            data=output.getvalue(),
            file_name="placement_glouton.xlsx"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)