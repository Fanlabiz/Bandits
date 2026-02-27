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
import random
from collections import defaultdict

print("=== DÉMARRAGE DE L'APPLICATION ===")

@dataclass
class Building:
    """Classe représentant un bâtiment"""
    name: str
    length: int
    width: int
    quantity: int
    culture: float
    radius: int
    boost_25: float
    boost_50: float
    boost_100: float
    
    def get_dimensions(self, orientation: str) -> Tuple[int, int]:
        """Retourne les dimensions selon l'orientation"""
        if orientation == 'H':
            return self.length, self.width
        else:  # 'V'
            return self.width, self.length
        
    def get_area(self) -> int:
        """Retourne la surface du bâtiment"""
        return self.length * self.width

class BuildingPlacer:
    """Classe principale pour le placement des bâtiments"""
    
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.boost_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.initialize_grids()
        
    def initialize_grids(self):
        """Initialise les grilles de placement avec la convention: 1=libre, 0=obstrué"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.boost_grid = np.zeros_like(self.terrain_grid, dtype=float)
        
        # CORRECTION: 0 = obstrué, 1 = libre
        self.placement_grid[self.terrain_grid == 0] = -1  # Cases obstruées (valeur 0)
        # Les cases avec 1 restent à 0 (libres)
        
        print(f"Statistiques terrain - Libres (1): {np.sum(self.terrain_grid == 1)}, Obstruées (0): {np.sum(self.terrain_grid == 0)}")
        
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
                        
                        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                            nx, ny = x + dx, y + dy
                            if (0 <= nx < self.placement_grid.shape[0] and 
                                0 <= ny < self.placement_grid.shape[1] and
                                self.placement_grid[nx, ny] == 0 and 
                                not visited[nx, ny]):
                                visited[nx, ny] = True
                                stack.append((nx, ny))
                    
                    if zone:
                        self.available_zones.append(zone)
        
        return len(self.available_zones)
    
    def can_place_building(self, x: int, y: int, length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé à la position donnée"""
        if x + length > self.placement_grid.shape[0] or y + width > self.placement_grid.shape[1]:
            return False
        
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        return True
    
    def can_place_in_zone(self, zone: List[Tuple[int, int]], x: int, y: int, 
                          length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé dans une zone spécifique"""
        zone_set = set(zone)
        
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in zone_set:
                    return False
        return True
    
    def calculate_boost_for_building(self, building: Building, x: int, y: int, 
                                    length: int, width: int) -> float:
        """Calcule le boost reçu par un bâtiment à la position donnée"""
        total_culture = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        # Cases dans le rayon
        for i in range(max(0, center_x - building.radius), 
                      min(self.placement_grid.shape[0], center_x + building.radius + 1)):
            for j in range(max(0, center_y - building.radius),
                          min(self.placement_grid.shape[1], center_y + building.radius + 1)):
                if self.placement_grid[i, j] > 0:
                    placed_building = self.placed_buildings[self.placement_grid[i, j] - 1]
                    total_culture += placed_building['building'].culture
        
        # Boost reçu
        if total_culture >= building.boost_100:
            return 2.0
        elif total_culture >= building.boost_50:
            return 1.5
        elif total_culture >= building.boost_25:
            return 1.25
        else:
            return 1.0
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        """Place un bâtiment sur le terrain"""
        length, width = building.get_dimensions(orientation)
        
        if not self.can_place_building(x, y, length, width):
            return False
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        placed_info = {
            'building': building,
            'x': x,
            'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id
        }
        self.placed_buildings.append(placed_info)
        return True
    
    def find_best_placement(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve la meilleure position dans une zone"""
        best_score = -1
        best_placement = None
        
        if not zone:
            return None
            
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        zone_size = len(zone)  # Définition de zone_size
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            # Vérifier si le bâtiment peut rentrer dans la zone
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        # Calculer le boost potentiel
                        boost = self.calculate_boost_for_building(building, x, y, length, width)
                        score = boost * building.culture
                        
                        # Bonus pour les positions centrales
                        center_x = (min_x + max_x) // 2
                        center_y = (min_y + max_y) // 2
                        building_center_x = x + length // 2
                        building_center_y = y + width // 2
                        center_dist = abs(building_center_x - center_x) + abs(building_center_y - center_y)
                        score += (zone_size - center_dist) * 0.1  # Léger bonus pour le centre
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'boost': boost, 'score': score
                            }
        
        return best_placement
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments en optimisant l'espace et les boosts"""
        self.initialize_grids()
        self.placed_buildings = []
        
        # Compter les bâtiments
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Créer une liste plate de tous les bâtiments à placer
        all_buildings = []
        for building in self.buildings:
            for _ in range(building.quantity):
                all_buildings.append(building)
        
        # Trier par importance : d'abord ceux qui produisent beaucoup (pour booster)
        all_buildings.sort(key=lambda b: (-b.culture, b.length * b.width))
        
        # Identifier les zones disponibles
        num_zones = self.find_available_zones()
        initial_free_cells = np.sum(self.placement_grid == 0)
        
        # Phase 1: Placement dans les grandes zones d'abord
        self.available_zones.sort(key=len, reverse=True)
        
        placed_count = 0
        for zone_idx, zone in enumerate(self.available_zones):
            zone_size = len(zone)
            
            # Prendre les bâtiments qui peuvent rentrer
            zone_buildings = []
            for building in all_buildings[:]:
                if building.get_area() <= zone_size:
                    zone_buildings.append(building)
                    all_buildings.remove(building)
            
            # Trier par productivité
            zone_buildings.sort(key=lambda b: -b.culture)
            
            # Placer dans la zone
            for building in zone_buildings:
                placement = self.find_best_placement(building, zone)
                if placement:
                    self.place_building(building, placement['x'], placement['y'], 
                                      placement['orientation'])
                    placed_count += 1
                    
                    # Mettre à jour la zone
                    new_zone = []
                    for (zx, zy) in zone:
                        if self.placement_grid[zx, zy] == 0:
                            new_zone.append((zx, zy))
                    zone = new_zone
                    zone_size = len(zone)
        
        # Phase 2: Tentative de placement des bâtiments restants
        if all_buildings:
            # Recalculer les zones
            self.find_available_zones()
            
            for building in all_buildings[:]:
                for zone in self.available_zones:
                    if building.get_area() <= len(zone):
                        placement = self.find_best_placement(building, zone)
                        if placement:
                            self.place_building(building, placement['x'], placement['y'], 
                                              placement['orientation'])
                            placed_count += 1
                            all_buildings.remove(building)
                            break
        
        # Calculer la production finale avec boosts
        total_production = 0
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        
        for placed in self.placed_buildings:
            building = placed['building']
            boost = self.calculate_boost_for_building(
                building, placed['x'], placed['y'],
                placed['length'], placed['width']
            )
            placed['current_boost'] = boost
            total_production += building.culture * boost
            
            # Statistiques des boosts
            if boost >= 2.0:
                boost_stats['100%'] += 1
            elif boost >= 1.5:
                boost_stats['50%'] += 1
            elif boost >= 1.25:
                boost_stats['25%'] += 1
            else:
                boost_stats['0%'] += 1
        
        # Statistiques d'occupation
        cells_occupied = np.sum(self.placement_grid > 0)
        cells_free = np.sum(self.placement_grid == 0)
        cells_obstructed = np.sum(self.placement_grid == -1)
        
        return {
            'total_production': total_production,
            'buildings_placed': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'cells_initial_free': initial_free_cells,
            'cells_occupied': cells_occupied,
            'cells_free': cells_free,
            'cells_obstructed': cells_obstructed
        }

def create_heatmap(grid: np.ndarray, title: str):
    """Crée une heatmap interactive avec Plotly"""
    # Créer une copie pour la visualisation
    viz_grid = grid.copy()
    
    fig = go.Figure(data=go.Heatmap(
        z=viz_grid,
        colorscale='Viridis',
        showscale=True,
        hoverongaps=False,
        text=viz_grid,
        texttemplate="%{text}",
        textfont={"size": 8}
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Colonne",
        yaxis_title="Ligne",
        height=700
    )
    return fig

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments")
st.markdown("""
Cette application optimise le placement de bâtiments sur un terrain pour maximiser la production avec les boosts.

**Convention du terrain :**
- **1** = Case libre (constructible)
- **0** = Case obstruée (non constructible)
""")

# Sidebar
with st.sidebar:
    st.header("📁 Chargement des données")
    uploaded_file = st.file_uploader(
        "Choisissez votre fichier Excel",
        type=['xlsx', 'xls'],
        help="Le fichier doit contenir deux onglets: terrain et bâtiments"
    )
    
    st.header("⚙️ Paramètres")
    optimize_button = st.button("🚀 Lancer l'optimisation", type="primary")

# Zone principale
if uploaded_file is None:
    st.info("👈 Veuillez charger un fichier Excel dans le menu latéral")
    
    st.subheader("📝 Format attendu")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Onglet 1 - Terrain** (1=libre, 0=obstrué)")
        example_terrain = pd.DataFrame([
            [1, 1, 0, 1, 1],
            [1, 1, 1, 1, 0],
            [0, 1, 1, 1, 1]
        ])
        st.dataframe(example_terrain)
    
    with col2:
        st.markdown("**Onglet 2 - Bâtiments**")
        example_buildings = pd.DataFrame({
            'Nom': ['Ferme', 'Atelier', 'Entrepôt'],
            'longueur': [2, 3, 2],
            'largeur': [2, 2, 3],
            'quantité': [2, 1, 1],
            'culture': [10, 15, 5],
            'rayonnement': [2, 3, 1],
            'Boost 25%': [5, 8, 3],
            'Boost 50%': [12, 15, 7],
            'Boost 100%': [20, 25, 12]
        })
        st.dataframe(example_buildings)

elif uploaded_file and optimize_button:
    try:
        with st.spinner("📊 Analyse du fichier..."):
            # Lecture des données
            df_terrain = pd.read_excel(uploaded_file, sheet_name=0, header=None, engine='openpyxl')
            df_buildings = pd.read_excel(uploaded_file, sheet_name=1, engine='openpyxl')
            
            terrain_grid = df_terrain.values.astype(int)
            
            # Vérification des valeurs
            unique_values = np.unique(terrain_grid)
            st.write(f"✅ Valeurs trouvées dans le terrain : {unique_values}")
            
            if 1 not in unique_values:
                st.warning("⚠️ Attention : Aucune case avec la valeur 1 (libre) trouvée !")
            
            # Création des bâtiments
            buildings = []
            for idx, row in df_buildings.iterrows():
                def get_value(possible_names, default=None):
                    for name in possible_names:
                        if name in row:
                            return row[name]
                    return default
                
                building = Building(
                    name=str(get_value(['Nom', 'nom', 'NAME', 'Batiment'], f"Bâtiment_{idx}")),
                    length=int(get_value(['longueur', 'Longueur', 'length'], 1)),
                    width=int(get_value(['largeur', 'Largeur', 'width'], 1)),
                    quantity=int(get_value(['quantité', 'Quantité', 'quantity'], 1)),
                    culture=float(get_value(['culture', 'Culture', 'prod'], 0)),
                    radius=int(get_value(['rayonnement', 'Rayonnement', 'radius'], 1)),
                    boost_25=float(get_value(['Boost 25%', 'boost_25'], 0)),
                    boost_50=float(get_value(['Boost 50%', 'boost_50'], 0)),
                    boost_100=float(get_value(['Boost 100%', 'boost_100'], 0))
                )
                buildings.append(building)
            
            total_demande = sum(b.quantity for b in buildings)
            
            # Statistiques initiales du terrain
            cells_libres = np.sum(terrain_grid == 1)
            cells_obstruees = np.sum(terrain_grid == 0)
            
            st.success(f"✅ {len(buildings)} types de bâtiments, {total_demande} unités à placer")
            st.info(f"🗺️ Terrain: {cells_libres} cases libres (1), {cells_obstruees} cases obstruées (0)")
            
            # Optimisation
            with st.spinner("⚙️ Optimisation en cours..."):
                placer = BuildingPlacer(terrain_grid, buildings)
                results = placer.place_all_buildings()
            
            # Affichage des résultats
            st.subheader("📊 Résultats de l'optimisation")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🏢 Bâtiments placés", 
                         f"{results['buildings_placed']}/{total_demande}",
                         f"{results['buildings_placed']/total_demande*100:.1f}%")
            with col2:
                st.metric("💰 Production totale", f"{results['total_production']:.0f}")
            with col3:
                utilisation = (results['cells_occupied'] / results['cells_initial_free']) * 100 if results['cells_initial_free'] > 0 else 0
                st.metric("📊 Utilisation espace", f"{utilisation:.1f}%")
            with col4:
                prod_moyenne = results['total_production'] / max(1, results['buildings_placed'])
                st.metric("📈 Production moyenne", f"{prod_moyenne:.1f}")
            
            # Statistiques des boosts
            st.subheader("⚡ Répartition des boosts")
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
            
            # Graphique des boosts
            fig_boost = go.Figure(data=[
                go.Bar(name='Bâtiments', 
                      x=['100%', '50%', '25%', '0%'],
                      y=[boost_stats['100%'], boost_stats['50%'], 
                         boost_stats['25%'], boost_stats['0%']],
                      marker_color=['gold', 'lightgreen', 'lightblue', 'lightgray'])
            ])
            fig_boost.update_layout(title="Distribution des boosts", height=400)
            st.plotly_chart(fig_boost, use_container_width=True)
            
            # Statistiques d'occupation détaillées
            st.subheader("📊 Occupation du terrain")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🟦 Cases occupées", results['cells_occupied'])
            with col2:
                st.metric("⬜ Cases libres restantes", results['cells_free'])
            with col3:
                st.metric("⬛ Cases obstruées (0)", results['cells_obstructed'])
            
            # Visualisation
            st.subheader("🗺️ Carte de placement")
            fig = create_heatmap(results['grid'], "Placement des bâtiments")
            st.plotly_chart(fig, use_container_width=True)
            
            # Tableau détaillé
            st.subheader("📋 Détail des placements")
            placement_data = []
            for placed in results['placed_buildings']:
                b = placed['building']
                placement_data.append({
                    'Bâtiment': b.name,
                    'Position': f"({placed['x']}, {placed['y']})",
                    'Orientation': placed['orientation'],
                    'Dimensions': f"{placed['length']}x{placed['width']}",
                    'Culture base': b.culture,
                    'Boost': f"{placed.get('current_boost', 1.0):.2f}x",
                    'Production': f"{b.culture * placed.get('current_boost', 1.0):.0f}"
                })
            
            df_results = pd.DataFrame(placement_data)
            st.dataframe(df_results, use_container_width=True)
            
            # Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_results.to_excel(writer, sheet_name='Placements', index=False)
                pd.DataFrame(results['grid']).to_excel(writer, sheet_name='Grille', 
                                                      index=False, header=False)
                
                stats = pd.DataFrame([{
                    'Batiments_places': results['buildings_placed'],
                    'Batiments_total': total_demande,
                    'Taux_placement': f"{results['buildings_placed']/total_demande*100:.1f}%",
                    'Production_totale': results['total_production'],
                    'Boost_100%': boost_stats['100%'],
                    'Boost_50%': boost_stats['50%'],
                    'Boost_25%': boost_stats['25%'],
                    'Sans_boost': boost_stats['0%'],
                    'Cases_occupees': results['cells_occupied'],
                    'Cases_libres': results['cells_free'],
                    'Cases_obstruees': results['cells_obstructed'],
                    'Utilisation_espace': f"{utilisation:.1f}%"
                }])
                stats.to_excel(writer, sheet_name='Statistiques', index=False)
            
            st.download_button(
                label="📥 Télécharger les résultats (Excel)",
                data=output.getvalue(),
                file_name="resultats_optimisation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)

print("=== APPLICATION PRÊTE ===")