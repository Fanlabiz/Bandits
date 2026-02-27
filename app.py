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
import heapq

print("=== DÉMARRAGE DE L'APPLICATION BOOST OPTIMISÉE ===")

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
    
    def get_boost_potential(self) -> float:
        """Retourne le potentiel de boost (plus c'est haut, plus ça booste les autres)"""
        return (self.boost_25 + self.boost_50 + self.boost_100) / 3

class BuildingPlacer:
    """Classe principale pour le placement des bâtiments avec optimisation des boosts"""
    
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.boost_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.boost_map = None  # Carte des boosts potentiels
        self.initialize_grids()
        
    def initialize_grids(self):
        """Initialise les grilles de placement"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.boost_grid = np.zeros_like(self.terrain_grid, dtype=float)
        self.boost_map = np.zeros_like(self.terrain_grid, dtype=float)
        self.placement_grid[self.terrain_grid == 1] = -1  # Cases obstruées
        
    def precalculate_boost_potential(self):
        """Précalcule le potentiel de boost de chaque case"""
        for i in range(self.terrain_grid.shape[0]):
            for j in range(self.terrain_grid.shape[1]):
                if self.placement_grid[i, j] == 0:
                    # Plus on est entouré de cases libres, plus on a de potentiel
                    free_neighbors = 0
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            ni, nj = i + di, j + dj
                            if (0 <= ni < self.terrain_grid.shape[0] and 
                                0 <= nj < self.terrain_grid.shape[1] and
                                self.placement_grid[ni, nj] == 0):
                                free_neighbors += 1
                    self.boost_map[i, j] = free_neighbors / 9  # Normalisé entre 0 et 1
        
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
    
    def calculate_boost_for_building(self, building: Building, x: int, y: int, 
                                    length: int, width: int) -> Tuple[float, float]:
        """
        Calcule deux choses:
        - boost_recu: ce que ce bâtiment reçoit des autres
        - boost_donne: ce que ce bâtiment donne aux autres (potentiel futur)
        """
        boost_recu = 0
        total_culture_around = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        # Cases dans le rayon
        for i in range(max(0, center_x - building.radius), 
                      min(self.terrain_grid.shape[0], center_x + building.radius + 1)):
            for j in range(max(0, center_y - building.radius),
                          min(self.terrain_grid.shape[1], center_y + building.radius + 1)):
                if self.placement_grid[i, j] > 0:
                    placed_building = self.placed_buildings[self.placement_grid[i, j] - 1]
                    total_culture_around += placed_building['building'].culture
        
        # Boost reçu
        if total_culture_around >= building.boost_100:
            boost_recu = 2.0
        elif total_culture_around >= building.boost_50:
            boost_recu = 1.5
        elif total_culture_around >= building.boost_25:
            boost_recu = 1.25
        else:
            boost_recu = 1.0
        
        # Boost donné (potentiel) - plus la culture est haute, plus ça booste les autres
        boost_donne = building.culture / 10  # Normalisé
        
        return boost_recu, boost_donne
    
    def can_place_building(self, x: int, y: int, length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé à la position donnée"""
        if x + length > self.terrain_grid.shape[0] or y + width > self.terrain_grid.shape[1]:
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
    
    def calculate_position_score(self, building: Building, x: int, y: int, 
                                length: int, width: int, 
                                weight_boost: float = 0.7) -> float:
        """
        Calcule un score pour une position en équilibrant:
        - Boost reçu par le bâtiment
        - Boost donné aux futurs bâtiments
        - Proximité d'autres bâtiments
        """
        boost_recu, boost_donne = self.calculate_boost_for_building(building, x, y, length, width)
        
        # Score basé sur la production avec boost
        production_score = building.culture * boost_recu
        
        # Score basé sur le boost donné aux autres
        boost_potential_score = boost_donne * 100  # Pondéré
        
        # Bonus pour être proche d'autres bâtiments (synergie)
        proximity_score = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        for placed in self.placed_buildings:
            pb = placed['building']
            dist = abs(center_x - (placed['x'] + placed['length']//2)) + \
                   abs(center_y - (placed['y'] + placed['width']//2))
            if dist <= building.radius + pb.radius:
                proximity_score += pb.culture / max(1, dist)
        
        # Combiner les scores
        total_score = (production_score + 
                      weight_boost * boost_potential_score + 
                      0.3 * proximity_score)
        
        return total_score
    
    def find_best_placement_with_boosts(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve la meilleure position en optimisant les boosts"""
        best_score = -1
        best_placement = None
        
        xs = [p[0] for p in zone]
        ys = [p[1] for p in zone]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            for x in range(min_x, max_x - length + 2):
                for y in range(min_y, max_y - width + 2):
                    if self.can_place_in_zone(zone, x, y, length, width):
                        score = self.calculate_position_score(building, x, y, length, width)
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'score': score
                            }
        
        return best_placement
    
    def place_all_buildings_boost_optimized(self) -> dict:
        """Place tous les bâtiments en optimisant les boosts"""
        self.initialize_grids()
        self.placed_buildings = []
        self.precalculate_boost_potential()
        
        # Statistiques
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Étape 1: Identifier les bâtiments "boosters" (ceux qui donnent beaucoup de culture)
        boosters = [b for b in self.buildings if b.culture > 10]
        normals = [b for b in self.buildings if b.culture <= 10]
        
        # Trier les boosters par culture (les plus productifs d'abord)
        boosters.sort(key=lambda b: -b.culture)
        
        # Créer la liste de tous les bâtiments à placer
        all_buildings = []
        for b in boosters:
            for _ in range(b.quantity):
                all_buildings.append(('booster', b))
        for b in normals:
            for _ in range(b.quantity):
                all_buildings.append(('normal', b))
        
        # Identifier les zones
        self.find_available_zones()
        st.info(f"🗺️ {len(self.available_zones)} zones libres identifiées")
        
        # Phase 1: Placer les boosters au centre des zones
        st.info("⚡ Phase 1: Placement des bâtiments boosters...")
        for zone_idx, zone in enumerate(self.available_zones):
            # Trouver le centre de la zone
            center_x = sum(p[0] for p in zone) // len(zone)
            center_y = sum(p[1] for p in zone) // len(zone)
            
            # Placer les boosters dans cette zone
            zone_boosters = [b for t, b in all_buildings if t == 'booster']
            for booster in zone_boosters[:2]:  # Max 2 boosters par zone
                placement = self.find_best_placement_with_boosts(booster, zone)
                if placement:
                    self.place_building(booster, placement['x'], placement['y'], 
                                      placement['orientation'])
                    # Retirer de la liste
                    for i, (t, b) in enumerate(all_buildings):
                        if t == 'booster' and b.name == booster.name:
                            all_buildings.pop(i)
                            break
        
        # Phase 2: Placer les bâtiments normaux autour des boosters
        st.info("🔄 Phase 2: Placement des bâtiments complémentaires...")
        
        # Recalculer les zones après placement des boosters
        self.find_available_zones()
        
        for building_type, building in all_buildings[:]:
            best_placement = None
            best_score = -1
            best_zone = None
            
            for zone in self.available_zones:
                placement = self.find_best_placement_with_boosts(building, zone)
                if placement and placement['score'] > best_score:
                    best_score = placement['score']
                    best_placement = placement
                    best_zone = zone
            
            if best_placement:
                self.place_building(building, best_placement['x'], best_placement['y'],
                                  best_placement['orientation'])
                # Mettre à jour la zone
                new_zone = []
                for (zx, zy) in best_zone:
                    if self.placement_grid[zx, zy] == 0:
                        new_zone.append((zx, zy))
                if new_zone:
                    self.available_zones[self.available_zones.index(best_zone)] = new_zone
                else:
                    self.available_zones.remove(best_zone)
        
        # Calculer la production finale avec boosts
        total_production = 0
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        
        for placed in self.placed_buildings:
            building = placed['building']
            boost_recu, _ = self.calculate_boost_for_building(
                building, placed['x'], placed['y'],
                placed['length'], placed['width']
            )
            placed['current_boost'] = boost_recu
            total_production += building.culture * boost_recu
            
            # Statistiques des boosts
            if boost_recu >= 2.0:
                boost_stats['100%'] += 1
            elif boost_recu >= 1.5:
                boost_stats['50%'] += 1
            elif boost_recu >= 1.25:
                boost_stats['25%'] += 1
            else:
                boost_stats['0%'] += 1
        
        return {
            'total_production': total_production,
            'buildings_placed': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'available_zones': len(self.available_zones)
        }

def create_heatmap(grid: np.ndarray, title: str):
    """Crée une heatmap interactive avec Plotly"""
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
        height=700,
        width=900
    )
    return fig

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments avec Boosts", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement avec Boosts Optimisés")
st.markdown("""
Cette version optimise à la fois le placement et les boosts :
1. **Phase 1** : Placement des bâtiments producteurs au centre des zones
2. **Phase 2** : Placement des autres bâtiments autour pour maximiser les boosts
3. **Calcul intelligent** : Équilibre entre production directe et boosts
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
if uploaded_file and optimize_button:
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
            st.success(f"✅ {len(buildings)} types de bâtiments, {total_demande} unités à placer")
            
            # Optimisation avec boosts
            with st.spinner("⚙️ Optimisation des boosts en cours..."):
                placer = BuildingPlacer(terrain_grid, buildings)
                results = placer.place_all_buildings_boost_optimized()
            
            # Affichage des résultats
            st.subheader("📊 Résultats de l'optimisation")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🏢 Bâtiments placés", 
                         f"{results['buildings_placed']}/{total_demande}")
            with col2:
                st.metric("💰 Production totale", f"{results['total_production']:.0f}")
            with col3:
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
                go.Bar(name='Nombre de bâtiments', 
                      x=['100%', '50%', '25%', '0%'],
                      y=[boost_stats['100%'], boost_stats['50%'], 
                         boost_stats['25%'], boost_stats['0%']])
            ])
            fig_boost.update_layout(title="Distribution des boosts")
            st.plotly_chart(fig_boost, use_container_width=True)
            
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
                    'Production_totale': results['total_production'],
                    'Boost_100%': boost_stats['100%'],
                    'Boost_50%': boost_stats['50%'],
                    'Boost_25%': boost_stats['25%'],
                    'Sans_boost': boost_stats['0%']
                }])
                stats.to_excel(writer, sheet_name='Statistiques', index=False)
            
            st.download_button(
                label="📥 Télécharger les résultats (Excel)",
                data=output.getvalue(),
                file_name="resultats_boosts.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)

elif uploaded_file is None:
    st.info("👈 Veuillez charger un fichier Excel dans le menu latéral")
    
    st.subheader("📝 Format attendu")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Onglet 1 - Terrain**")
        example_terrain = pd.DataFrame([
            [0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0]
        ])
        st.dataframe(example_terrain)
    with col2:
        st.markdown("**Onglet 2 - Bâtiments**")
        example_buildings = pd.DataFrame({
            'Nom': ['Ferme', 'Atelier'],
            'longueur': [2, 3],
            'largeur': [2, 2],
            'quantité': [2, 1],
            'culture': [10, 15],
            'rayonnement': [2, 3],
            'Boost 25%': [5, 8],
            'Boost 50%': [12, 15],
            'Boost 100%': [20, 25]
        })
        st.dataframe(example_buildings)

print("=== APPLICATION PRÊTE ===")