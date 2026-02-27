"""Application Streamlit pour placement de bâtiments avec optimisation avancée des boosts"""
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
import heapq

print("=== DÉMARRAGE DE L'APPLICATION BOOST OPTIMISÉE V2 ===")

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
        if orientation == 'H':
            return self.length, self.width
        else:
            return self.width, self.length
        
    def get_area(self) -> int:
        return self.length * self.width
    
    def get_boost_thresholds(self):
        """Retourne les seuils de boost"""
        return {
            '25%': self.boost_25,
            '50%': self.boost_50,
            '100%': self.boost_100
        }

class BoostOptimizer:
    """Classe dédiée à l'optimisation des boosts"""
    
    def __init__(self, buildings: List[Building]):
        self.buildings = buildings
        self.boost_network = defaultdict(list)  # Graphe des boosts potentiels
        
    def calculate_boost_potential(self, producer: Building, consumer: Building) -> float:
        """Calcule le potentiel de boost d'un producteur sur un consommateur"""
        if producer.culture == 0:
            return 0
        
        # Plus le producteur produit, plus il booste
        # Plus le consommateur a des seuils bas, plus c'est facile à booster
        avg_threshold = (consumer.boost_25 + consumer.boost_50 + consumer.boost_100) / 3
        if avg_threshold == 0:
            return 0
            
        return (producer.culture / avg_threshold) * 100
    
    def build_boost_network(self):
        """Construit le réseau de boosts potentiels"""
        for producer in self.buildings:
            if producer.culture > 0:  # Producteur
                for consumer in self.buildings:
                    if consumer.name != producer.name:  # Pas auto-boost
                        potential = self.calculate_boost_potential(producer, consumer)
                        if potential > 0:
                            self.boost_network[producer.name].append({
                                'consumer': consumer,
                                'potential': potential
                            })
        
        # Trier par potentiel
        for key in self.boost_network:
            self.boost_network[key].sort(key=lambda x: -x['potential'])

class BuildingPlacer:
    """Classe principale pour le placement des bâtiments"""
    
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.boost_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.boost_optimizer = BoostOptimizer(buildings)
        self.boost_optimizer.build_boost_network()
        self.initialize_grids()
        
    def initialize_grids(self):
        """Initialise les grilles avec convention: 1=libre, 0=obstrué"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.boost_grid = np.zeros_like(self.terrain_grid, dtype=float)
        self.placement_grid[self.terrain_grid == 0] = -1  # Cases obstruées
        
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
        """Vérifie si un bâtiment peut être placé"""
        if x + length > self.placement_grid.shape[0] or y + width > self.placement_grid.shape[1]:
            return False
        
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        return True
    
    def can_place_in_zone(self, zone: List[Tuple[int, int]], x: int, y: int, 
                          length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé dans une zone"""
        zone_set = set(zone)
        
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in zone_set:
                    return False
        return True
    
    def calculate_boost_for_building(self, building: Building, x: int, y: int, 
                                    length: int, width: int) -> Tuple[float, float, List]:
        """
        Calcule:
        - boost reçu par ce bâtiment
        - boost donné aux autres (potentiel futur)
        - liste des bâtiments qui le boostent
        """
        total_culture = 0
        boost_given = 0
        boosters = []
        
        center_x = x + length // 2
        center_y = y + width // 2
        
        # Parcourir toutes les cases dans le rayon
        for i in range(max(0, center_x - building.radius), 
                      min(self.placement_grid.shape[0], center_x + building.radius + 1)):
            for j in range(max(0, center_y - building.radius),
                          min(self.placement_grid.shape[1], center_y + building.radius + 1)):
                if self.placement_grid[i, j] > 0:
                    placed = self.placed_buildings[self.placement_grid[i, j] - 1]
                    total_culture += placed['building'].culture
                    boosters.append(placed['building'].name)
                    
                    # Ce bâtiment donne aussi du boost aux autres
                    if building.culture > 0:
                        boost_given += building.culture
        
        # Déterminer le boost reçu
        if total_culture >= building.boost_100:
            boost_received = 2.0
        elif total_culture >= building.boost_50:
            boost_received = 1.5
        elif total_culture >= building.boost_25:
            boost_received = 1.25
        else:
            boost_received = 1.0
        
        # Calculer le déficit pour atteindre le prochain palier
        if boost_received == 1.0:
            deficit_25 = max(0, building.boost_25 - total_culture)
        elif boost_received == 1.25:
            deficit_50 = max(0, building.boost_50 - total_culture)
        elif boost_received == 1.5:
            deficit_100 = max(0, building.boost_100 - total_culture)
        
        return boost_received, boost_given, boosters
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        """Place un bâtiment"""
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
    
    def find_boost_clusters(self) -> List[List[Building]]:
        """Identifie les clusters de bâtiments qui se boostent mutuellement"""
        clusters = []
        visited = set()
        
        # Créer un graphe des relations de boost
        for building in self.buildings:
            if building.name in visited:
                continue
                
            cluster = [building]
            visited.add(building.name)
            
            # Chercher les bâtiments qui se boostent mutuellement
            for other in self.buildings:
                if other.name not in visited:
                    potential = self.boost_optimizer.calculate_boost_potential(building, other)
                    if potential > 50:  # Seuil de 50% de potentiel
                        cluster.append(other)
                        visited.add(other.name)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        return clusters
    
    def find_best_placement_with_boost(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve la meilleure position en optimisant les boosts"""
        best_score = -1
        best_placement = None
        
        if not zone:
            return None
            
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Calculer le centre de la zone
        center_x = (min_x + max_x) // 2
        center_y = (min_y + max_y) // 2
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            # Vérifier si le bâtiment peut rentrer
            if length > (max_x - min_x + 1) or width > (max_y - min_y + 1):
                continue
                
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        # Calculer les boosts
                        boost_received, boost_given, boosters = self.calculate_boost_for_building(
                            building, x, y, length, width
                        )
                        
                        # Score basé sur:
                        # 1. Production avec boost
                        production_score = building.culture * boost_received
                        
                        # 2. Boost donné aux autres
                        boost_score = boost_given * 0.5
                        
                        # 3. Proximité du centre (pour regrouper les bâtiments)
                        building_center_x = x + length // 2
                        building_center_y = y + width // 2
                        center_dist = abs(building_center_x - center_x) + abs(building_center_y - center_y)
                        proximity_score = (len(zone) - center_dist) * 0.1
                        
                        # 4. Bonus si ce bâtiment complète un cluster de boost
                        cluster_bonus = 0
                        if len(boosters) > 0:
                            cluster_bonus = len(boosters) * 10
                        
                        # Score total
                        score = production_score + boost_score + proximity_score + cluster_bonus
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'boost_received': boost_received,
                                'boost_given': boost_given,
                                'boosters': boosters,
                                'score': score
                            }
        
        return best_placement
    
    def place_all_buildings_optimized(self) -> dict:
        """Place tous les bâtiments avec optimisation maximale des boosts"""
        self.initialize_grids()
        self.placed_buildings = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Étape 1: Identifier les clusters de boost
        clusters = self.find_boost_clusters()
        st.info(f"🔗 {len(clusters)} clusters de boost identifiés")
        
        # Étape 2: Créer une liste de tous les bâtiments avec leurs priorités
        building_queue = []
        for building in self.buildings:
            for i in range(building.quantity):
                # Priorité basée sur:
                # - Culture (productivité)
                # - Potentiel de boost donné
                # - Facilité à être boosté (seuils bas)
                avg_threshold = (building.boost_25 + building.boost_50 + building.boost_100) / 3
                boost_potential = building.culture / max(1, avg_threshold)
                
                priority = building.culture * 2 + boost_potential
                building_queue.append({
                    'building': building,
                    'priority': priority,
                    'cluster': None
                })
        
        # Assigner les clusters
        for item in building_queue:
            for cluster in clusters:
                if item['building'] in cluster:
                    item['cluster'] = cluster
                    break
        
        # Trier par priorité
        building_queue.sort(key=lambda x: -x['priority'])
        
        # Étape 3: Identifier les zones
        self.find_available_zones()
        initial_free_cells = np.sum(self.placement_grid == 0)
        
        # Étape 4: Placement phase 1 - Les bâtiments des clusters ensemble
        st.info("🎯 Phase 1: Placement des clusters de boost...")
        
        # Grouper par cluster
        cluster_buildings = defaultdict(list)
        for item in building_queue:
            if item['cluster']:
                cluster_buildings[id(item['cluster'])].append(item)
        
        for cluster_id, items in cluster_buildings.items():
            # Prendre la plus grande zone disponible
            if not self.available_zones:
                break
                
            best_zone = max(self.available_zones, key=len)
            self.available_zones.remove(best_zone)
            
            # Placer les bâtiments du cluster dans cette zone
            for item in items:
                placement = self.find_best_placement_with_boost(item['building'], best_zone)
                if placement:
                    self.place_building(item['building'], placement['x'], placement['y'],
                                      placement['orientation'])
                    
                    # Mettre à jour la zone
                    new_zone = []
                    for (zx, zy) in best_zone:
                        if self.placement_grid[zx, zy] == 0:
                            new_zone.append((zx, zy))
                    best_zone = new_zone
                    
                    # Retirer de la queue
                    building_queue.remove(item)
        
        # Étape 5: Phase 2 - Placement des bâtiments restants
        st.info("🔄 Phase 2: Placement des bâtiments complémentaires...")
        
        # Recalculer les zones
        self.find_available_zones()
        
        for item in building_queue[:]:
            building = item['building']
            best_placement = None
            best_score = -1
            best_zone_idx = -1
            
            for zone_idx, zone in enumerate(self.available_zones):
                if building.get_area() <= len(zone):
                    placement = self.find_best_placement_with_boost(building, zone)
                    if placement and placement['score'] > best_score:
                        best_score = placement['score']
                        best_placement = placement
                        best_zone_idx = zone_idx
            
            if best_placement:
                self.place_building(building, best_placement['x'], best_placement['y'],
                                  best_placement['orientation'])
                building_queue.remove(item)
                
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
        
        # Calculer la production finale avec boosts
        total_production = 0
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        boost_details = []
        
        for placed in self.placed_buildings:
            building = placed['building']
            boost_received, boost_given, boosters = self.calculate_boost_for_building(
                building, placed['x'], placed['y'],
                placed['length'], placed['width']
            )
            placed['current_boost'] = boost_received
            placed['boosters'] = boosters
            total_production += building.culture * boost_received
            
            # Statistiques
            if boost_received >= 2.0:
                boost_stats['100%'] += 1
            elif boost_received >= 1.5:
                boost_stats['50%'] += 1
            elif boost_received >= 1.25:
                boost_stats['25%'] += 1
            else:
                boost_stats['0%'] += 1
            
            boost_details.append({
                'building': building.name,
                'boost': boost_received,
                'boosters': len(boosters)
            })
        
        # Statistiques d'occupation
        cells_occupied = np.sum(self.placement_grid > 0)
        cells_free = np.sum(self.placement_grid == 0)
        cells_obstructed = np.sum(self.placement_grid == -1)
        
        # Statistiques des boosters
        avg_boosters = np.mean([len(b['boosters']) for b in self.placed_buildings]) if self.placed_buildings else 0
        
        return {
            'total_production': total_production,
            'buildings_placed': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'buildings_remaining': len(building_queue),
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'boost_details': boost_details,
            'avg_boosters': avg_boosters,
            'cells_initial_free': initial_free_cells,
            'cells_occupied': cells_occupied,
            'cells_free': cells_free,
            'cells_obstructed': cells_obstructed
        }

def create_heatmap(grid: np.ndarray, title: str):
    """Crée une heatmap interactive"""
    fig = go.Figure(data=go.Heatmap(
        z=grid,
        colorscale='Viridis',
        showscale=True,
        hoverongaps=False,
        text=grid,
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
st.set_page_config(page_title="Optimiseur de Bâtiments V2", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments - Version Boost Optimisée")
st.markdown("""
Cette version utilise un algorithme avancé qui :
1. **Identifie les clusters de bâtiments** qui se boostent mutuellement
2. **Place les clusters ensemble** pour maximiser les synergies
3. **Optimise chaque placement** pour le boost reçu ET donné
4. **Priorise les bâtiments** selon leur potentiel de boost
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
    optimize_button = st.button("🚀 Lancer l'optimisation avancée", type="primary")

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
            cells_libres = np.sum(terrain_grid == 1)
            
            st.success(f"✅ {len(buildings)} types de bâtiments, {total_demande} unités à placer")
            st.info(f"🗺️ Terrain: {cells_libres} cases libres")
            
            # Optimisation avancée
            with st.spinner("⚙️ Optimisation avancée en cours (cela peut prendre quelques secondes)..."):
                placer = BuildingPlacer(terrain_grid, buildings)
                results = placer.place_all_buildings_optimized()
            
            # Affichage des résultats
            st.subheader("📊 Résultats de l'optimisation avancée")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🏢 Bâtiments placés", 
                         f"{results['buildings_placed']}/{total_demande}",
                         f"{results['buildings_placed']/total_demande*100:.1f}%")
            with col2:
                st.metric("💰 Production totale", f"{results['total_production']:.0f}")
            with col3:
                st.metric("📊 Boost moyen", f"{results['total_production']/max(1, results['buildings_placed'])/10:.2f}x")
            with col4:
                st.metric("🔄 Boosters par bâtiment", f"{results['avg_boosters']:.1f}")
            
            # Statistiques des boosts
            st.subheader("⚡ Distribution des boosts")
            boost_stats = results['boost_stats']
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("🔥 Boost 100%", boost_stats['100%'], 
                         f"{boost_stats['100%']/results['buildings_placed']*100:.1f}%")
            with col2:
                st.metric("✨ Boost 50%", boost_stats['50%'],
                         f"{boost_stats['50%']/results['buildings_placed']*100:.1f}%")
            with col3:
                st.metric("⭐ Boost 25%", boost_stats['25%'],
                         f"{boost_stats['25%']/results['buildings_placed']*100:.1f}%")
            with col4:
                st.metric("⚪ Sans boost", boost_stats['0%'],
                         f"{boost_stats['0%']/results['buildings_placed']*100:.1f}%")
            
            # Graphique des boosts
            fig_boost = go.Figure(data=[
                go.Bar(name='Bâtiments', 
                      x=['100%', '50%', '25%', '0%'],
                      y=[boost_stats['100%'], boost_stats['50%'], 
                         boost_stats['25%'], boost_stats['0%']],
                      marker_color=['gold', 'lightgreen', 'lightblue', 'lightgray'],
                      text=[f"{boost_stats['100%']/results['buildings_placed']*100:.1f}%",
                           f"{boost_stats['50%']/results['buildings_placed']*100:.1f}%",
                           f"{boost_stats['25%']/results['buildings_placed']*100:.1f}%",
                           f"{boost_stats['0%']/results['buildings_placed']*100:.1f}%"],
                      textposition='auto')
            ])
            fig_boost.update_layout(title="Distribution des boosts", height=400)
            st.plotly_chart(fig_boost, use_container_width=True)
            
            # Détail des boosts par bâtiment
            st.subheader("📋 Détail des boosts par bâtiment")
            boost_df = pd.DataFrame(results['boost_details'])
            if not boost_df.empty:
                boost_df['pourcentage'] = (boost_df['boost'] - 1) * 100
                st.dataframe(boost_df, use_container_width=True)
            
            # Visualisation
            st.subheader("🗺️ Carte de placement")
            fig = create_heatmap(results['grid'], "Placement des bâtiments")
            st.plotly_chart(fig, use_container_width=True)
            
            # Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Placements détaillés
                placement_data = []
                for placed in results['placed_buildings']:
                    b = placed['building']
                    placement_data.append({
                        'Bâtiment': b.name,
                        'Position_X': placed['x'],
                        'Position_Y': placed['y'],
                        'Orientation': placed['orientation'],
                        'Dimensions': f"{placed['length']}x{placed['length']}",
                        'Culture_base': b.culture,
                        'Boost': placed.get('current_boost', 1.0),
                        'Production': b.culture * placed.get('current_boost', 1.0),
                        'Boosters': len(placed.get('boosters', []))
                    })
                
                pd.DataFrame(placement_data).to_excel(writer, sheet_name='Placements', index=False)
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
                    'Boost_moyen': f"{results['total_production']/max(1, results['buildings_placed'])/10:.2f}x",
                    'Boosters_moyen': f"{results['avg_boosters']:.1f}"
                }])
                stats.to_excel(writer, sheet_name='Statistiques', index=False)
            
            st.download_button(
                label="📥 Télécharger les résultats complets (Excel)",
                data=output.getvalue(),
                file_name="resultats_boosts_optimises.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)

print("=== APPLICATION PRÊTE ===")