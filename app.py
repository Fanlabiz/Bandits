"""Application Streamlit pour placement de bâtiments avec optimisation"""
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

print("=== DÉMARRAGE DE L'APPLICATION COMPLÈTE ===")

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

class BuildingPlacer:
    """Classe principale pour le placement des bâtiments"""
    
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.boost_grid = None
        self.placed_buildings = []
        self.initialize_grids()
        
    def initialize_grids(self):
        """Initialise les grilles de placement"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
        self.boost_grid = np.zeros_like(self.terrain_grid, dtype=float)
        self.placement_grid[self.terrain_grid == 1] = -1  # Cases obstruées
    
    def can_place_building(self, x: int, y: int, length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé à la position donnée"""
        if x + length > self.terrain_grid.shape[0] or y + width > self.terrain_grid.shape[1]:
            return False
        
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        return True
    
    def calculate_boost(self, building: Building, x: int, y: int, 
                       length: int, width: int) -> float:
        """Calcule le boost pour un bâtiment à la position donnée"""
        total_culture = 0
        center_x = x + length // 2
        center_y = y + width // 2
        
        for i in range(max(0, center_x - building.radius), 
                      min(self.terrain_grid.shape[0], center_x + building.radius + 1)):
            for j in range(max(0, center_y - building.radius),
                          min(self.terrain_grid.shape[1], center_y + building.radius + 1)):
                if self.placement_grid[i, j] > 0:
                    placed_building = self.placed_buildings[self.placement_grid[i, j] - 1]
                    total_culture += placed_building['building'].culture
        
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
    
    def find_best_placement(self, building: Building) -> Optional[dict]:
        """Trouve la meilleure position pour un bâtiment"""
        best_score = -1
        best_placement = None
        
        for orientation in ['H', 'V']:
            length, width = building.get_dimensions(orientation)
            
            for x in range(self.terrain_grid.shape[0] - length + 1):
                for y in range(self.terrain_grid.shape[1] - width + 1):
                    if self.can_place_building(x, y, length, width):
                        boost = self.calculate_boost(building, x, y, length, width)
                        score = boost * building.culture
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation,
                                'boost': boost, 'score': score
                            }
        return best_placement
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments en optimisant les boosts"""
        self.initialize_grids()
        self.placed_buildings = []
        
        # Trier par importance (ceux qui boostent en premier)
        sorted_buildings = sorted(self.buildings, 
                                 key=lambda b: b.boost_100, 
                                 reverse=True)
        
        placement_log = []
        
        for building in sorted_buildings:
            placed_count = 0
            for _ in range(building.quantity):
                placement = self.find_best_placement(building)
                
                if placement:
                    self.place_building(building, placement['x'], placement['y'], 
                                      placement['orientation'])
                    placed_count += 1
                    placement_log.append({
                        'building': building.name,
                        'x': placement['x'], 'y': placement['y'],
                        'orientation': placement['orientation'],
                        'boost': placement['boost']
                    })
                else:
                    break
        
        # Calculer la production finale
        total_production = 0
        for placed in self.placed_buildings:
            building = placed['building']
            boost = self.calculate_boost(building, placed['x'], placed['y'],
                                       placed['length'], placed['width'])
            placed['current_boost'] = boost
            total_production += building.culture * boost
        
        return {
            'total_production': total_production,
            'buildings_placed': len(self.placed_buildings),
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'placement_log': placement_log
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
        textfont={"size": 10}
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Colonne",
        yaxis_title="Ligne",
        height=600
    )
    return fig

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments")
st.markdown("""
Cette application optimise le placement de bâtiments sur un terrain 
pour maximiser les boosts de production.
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
        st.markdown("**Onglet 1 - Terrain** (0=libre, 1=obstrué)")
        example_terrain = pd.DataFrame([
            [0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0]
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
            df_terrain = pd.read_excel(uploaded_file, sheet_name=0, header=None)
            df_buildings = pd.read_excel(uploaded_file, sheet_name=1)
            
            terrain_grid = df_terrain.values.astype(int)
            
            # Création des objets Building
            buildings = []
            for _, row in df_buildings.iterrows():
                building = Building(
                    name=row['Nom'],
                    length=int(row['longueur']),
                    width=int(row['largeur']),
                    quantity=int(row['quantité']),
                    culture=float(row['culture']),
                    radius=int(row['rayonnement']),
                    boost_25=float(row['Boost 25%']),
                    boost_50=float(row['Boost 50%']),
                    boost_100=float(row['Boost 100%'])
                )
                buildings.append(building)
            
            st.success("✅ Fichier chargé avec succès!")
            
            # Optimisation
            with st.spinner("⚙️ Optimisation en cours..."):
                placer = BuildingPlacer(terrain_grid, buildings)
                results = placer.place_all_buildings()
            
            # Affichage des résultats
            st.subheader("📊 Résultats de l'optimisation")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🏢 Bâtiments placés", 
                         results['buildings_placed'],
                         f"Total: {sum(b.quantity for b in buildings)}")
            with col2:
                st.metric("📈 Production totale", 
                         f"{results['total_production']:.2f}")
            with col3:
                occupation = (np.sum(results['grid'] > 0) / results['grid'].size) * 100
                st.metric("📊 Taux d'occupation", f"{occupation:.1f}%")
            
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
                    'Position (X,Y)': f"({placed['x']}, {placed['y']})",
                    'Orientation': placed['orientation'],
                    'Dimensions': f"{placed['length']}x{placed['width']}",
                    'Culture base': b.culture,
                    'Boost': f"{placed.get('current_boost', 1.0):.2f}x",
                    'Production': f"{b.culture * placed.get('current_boost', 1.0):.2f}"
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
                    'Production totale': results['total_production'],
                    'Bâtiments placés': results['buildings_placed'],
                    'Taux occupation': f"{occupation:.1f}%"
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