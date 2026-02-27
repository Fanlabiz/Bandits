"""Application Streamlit pour placement de bâtiments avec visualisation améliorée"""
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

print("=== DÉMARRAGE DE L'APPLICATION ===")

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

class BuildingPlacer:
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.producer_positions = []
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
        # Vérifier d'abord les limites
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
    
    def calculate_culture_in_radius(self, x: int, y: int, length: int, width: int, 
                                   radius: int) -> Tuple[float, List[str]]:
        total_culture = 0
        sources = []
        center_x = x + length // 2
        center_y = y + width // 2
        
        for px, py, p_building, p_id, p_radius in self.producer_positions:
            dist = abs(center_x - px) + abs(center_y - py)
            if dist <= radius:
                total_culture += p_building.culture_produced
                sources.append(p_building.name)
        
        return total_culture, sources
    
    def find_spot_in_radius(self, building: Building, zone: List[Tuple[int, int]], 
                           target_producer: Tuple) -> Optional[dict]:
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
                        center_x = x + length // 2
                        center_y = y + width // 2
                        dist = abs(center_x - px) + abs(center_y - py)
                        
                        if dist <= p_radius:
                            culture, sources = self.calculate_culture_in_radius(x, y, length, width, 
                                                                               building.radius)
                            # Score basé sur la culture reçue et la proximité
                            score = culture * 100 + (p_radius - dist) * 10
                            
                            if score > best_score:
                                best_score = score
                                best_placement = {
                                    'x': x, 'y': y, 'orientation': orientation,
                                    'culture': culture, 'sources': sources
                                }
        
        return best_placement
    
    def find_any_spot(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve n'importe quel spot disponible dans la zone"""
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
                        return {
                            'x': x, 'y': y, 'orientation': orientation,
                            'culture': 0, 'sources': []
                        }
        return None
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        length, width = building.get_dimensions(orientation)
        
        # Vérification finale avant placement
        for i in range(length):
            for j in range(width):
                if self.placement_grid[x + i, y + j] != 0:
                    return False
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer la culture reçue
        culture_recue, sources = self.calculate_culture_in_radius(x, y, length, width, 
                                                                  building.radius if building.can_be_boosted() else 0)
        
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
        
        if building.is_producer():
            center_x = x + length // 2
            center_y = y + width // 2
            self.producer_positions.append((center_x, center_y, building, building_id, building.radius))
        
        return True
    
    def place_all_buildings(self) -> dict:
        self.initialize_grids()
        self.placed_buildings = []
        self.producer_positions = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
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
        consumers.sort(key=lambda b: (b.boost_25 if b.boost_25 > 0 else 99999))
        
        # Identifier les zones disponibles
        self.find_available_zones()
        initial_free = np.sum(self.placement_grid == 0)
        
        # PHASE 1: Placer les producteurs au centre des grandes zones
        st.info("📌 Phase 1: Placement des producteurs...")
        self.available_zones.sort(key=len, reverse=True)
        
        for producer in producers[:]:
            if not self.available_zones:
                break
                
            # Prendre la plus grande zone
            zone = self.available_zones[0]
            xs = [p[0] for p in zone]
            ys = [p[1] for p in zone]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            # Essayer de placer près du centre
            center_x = (min_x + max_x) // 2
            center_y = (min_y + max_y) // 2
            
            placed = False
            for orientation in ['H', 'V']:
                length, width = producer.get_dimensions(orientation)
                
                # Essayer différentes positions autour du centre
                for dx in [-2, -1, 0, 1, 2]:
                    for dy in [-2, -1, 0, 1, 2]:
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
                    self.available_zones[0] = new_zone
                else:
                    self.available_zones.pop(0)
                
                # Retrier les zones
                self.available_zones.sort(key=len, reverse=True)
        
        # PHASE 2: Placer les consommateurs autour des producteurs
        st.info("📌 Phase 2: Placement des consommateurs dans les rayons...")
        
        # Recalculer les zones après placement des producteurs
        self.find_available_zones()
        
        consumers_placed_in_radius = 0
        for consumer in consumers[:]:
            best_placement = None
            best_culture = -1
            best_zone_idx = -1
            
            # Chercher dans toutes les zones
            for zone_idx, zone in enumerate(self.available_zones):
                # Essayer chaque producteur
                for producer_data in self.producer_positions:
                    placement = self.find_spot_in_radius(consumer, zone, producer_data)
                    if placement and placement['culture'] > best_culture:
                        best_culture = placement['culture']
                        best_placement = placement
                        best_zone_idx = zone_idx
            
            if best_placement:
                if self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                     best_placement['orientation']):
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
        
        # PHASE 3: Placer le reste (bâtiments non placés)
        remaining = producers + consumers
        if remaining:
            st.info(f"📌 Phase 3: Placement des {len(remaining)} bâtiments restants...")
            
            for building in remaining:
                placed = False
                for zone_idx, zone in enumerate(self.available_zones):
                    if placed:
                        break
                    
                    placement = self.find_any_spot(building, zone)
                    if placement:
                        if self.place_building(building, placement['x'], placement['y'], 
                                             placement['orientation']):
                            placed = True
                            
                            # Mettre à jour la zone
                            new_zone = []
                            for (zx, zy) in zone:
                                if self.placement_grid[zx, zy] == 0:
                                    new_zone.append((zx, zy))
                            
                            if new_zone:
                                self.available_zones[zone_idx] = new_zone
                            else:
                                self.available_zones.pop(zone_idx)
                            break
        
        # Calculer les statistiques finales
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
            'initial_free': initial_free,
            'occupied': np.sum(self.placement_grid > 0),
            'free': np.sum(self.placement_grid == 0),
            'obstructed': np.sum(self.placement_grid == -1)
        }

def create_colorful_heatmap(grid: np.ndarray, placed_buildings: List[dict], title: str):
    """
    Crée une visualisation colorée avec:
    - Cases obstruées (-1) en GRIS FONCÉ
    - Cases libres (0) en BLANC
    - Chaque bâtiment avec une couleur DIFFÉRENTE
    """
    
    # Palette de couleurs pour les bâtiments
    colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEEAD', '#D4A5A5',
        '#9B59B6', '#3498DB', '#E67E22', '#2ECC71', '#E74C3C', '#1ABC9C',
        '#F1C40F', '#E67E22', '#9B59B6', '#34495E', '#16A085', '#27AE60',
        '#2980B9', '#8E44AD', '#F39C12', '#D35400', '#C0392B', '#BDC3C7',
        '#7F8C8D', '#2C3E50', '#E74C3C', '#3498DB', '#1ABC9C', '#F1C40F',
        '#E67E22', '#9B59B6', '#34495E', '#16A085', '#27AE60', '#2980B9'
    ]
    
    # Créer un mapping building_id -> couleur
    building_colors = {}
    for i, placed in enumerate(placed_buildings):
        building_id = placed['building_id']
        building_colors[building_id] = colors[i % len(colors)]
    
    # Créer le heatmap
    fig = go.Figure()
    
    # Ajouter le heatmap
    fig.add_trace(go.Heatmap(
        z=grid,
        colorscale=[
            [0, 'white'],           # Cases libres (0)
            [0.001, 'white'],
            [0.001, 'darkgray'],    # Cases obstruées (-1)
            [0.5, 'darkgray'],
            [0.5, '#FF6B6B'],       # Bâtiments (valeurs > 0)
            [1, '#FF6B6B']
        ],
        showscale=False,
        hoverongaps=False,
        text=grid,
        texttemplate="%{text}",
        textfont={"size": 8, "color": "black"},
        hovertemplate='<b>Case</b><br>Valeur: %{z}<br>X: %{x}<br>Y: %{y}<extra></extra>'
    ))
    
    # Ajouter des annotations pour les bâtiments
    annotations = []
    for placed in placed_buildings:
        building_id = placed['building_id']
        x = placed['x']
        y = placed['y']
        
        # Calculer le centre du bâtiment
        center_x = y + placed['width'] // 2  # Note: inversion pour plotly
        center_y = x + placed['length'] // 2
        
        # Déterminer le niveau de boost pour la couleur du texte
        boost = placed.get('boost', 1.0)
        if boost >= 2.0:
            text_color = 'gold'
            border_color = 'darkgoldenrod'
        elif boost >= 1.5:
            text_color = 'lightgreen'
            border_color = 'darkgreen'
        elif boost >= 1.25:
            text_color = 'lightblue'
            border_color = 'darkblue'
        else:
            text_color = 'lightgray'
            border_color = 'gray'
        
        # Ajouter une annotation
        annotations.append(dict(
            x=center_x,
            y=center_y,
            text=placed['building'].name[:3],  # Abréviation
            showarrow=False,
            font=dict(size=10, color='black', family='Arial Black'),
            bgcolor=text_color,
            bordercolor=border_color,
            borderwidth=2,
            opacity=0.9
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Colonne",
        yaxis_title="Ligne",
        height=800,
        width=1000,
        annotations=annotations,
        yaxis=dict(autorange='reversed')
    )
    
    return fig

def create_building_summary(placed_buildings: List[dict]) -> pd.DataFrame:
    """Crée un résumé des bâtiments placés"""
    summary = []
    for p in placed_buildings:
        if p['building'].can_be_boosted():
            if p['culture_recue'] >= p['building'].boost_100:
                boost_level = "🔥 100%"
            elif p['culture_recue'] >= p['building'].boost_50:
                boost_level = "✨ 50%"
            elif p['culture_recue'] >= p['building'].boost_25:
                boost_level = "⭐ 25%"
            else:
                boost_level = "⚪ 0%"
            
            summary.append({
                'ID': p['building_id'],
                'Bâtiment': p['building'].name,
                'Type': '🏭 Producteur' if p['building'].is_producer() else '🏠 Consommateur',
                'Position': f"({p['x']}, {p['y']})",
                'Dimensions': f"{p['length']}x{p['width']}",
                'Culture reçue': f"{p['culture_recue']:.0f}",
                'Boost': boost_level,
                'Sources': len(p['sources'])
            })
    return pd.DataFrame(summary)

# Interface Streamlit
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments")

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
        fig = create_colorful_heatmap(results['grid'], results['placed_buildings'], 
                                     "Placement des bâtiments")
        st.plotly_chart(fig, use_container_width=True)
        
        # Tableau récapitulatif
        st.subheader("📋 Résumé des bâtiments")
        df_summary = create_building_summary(results['placed_buildings'])
        st.dataframe(df_summary, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='Placements', index=False)
            pd.DataFrame(results['grid']).to_excel(writer, sheet_name='Grille', index=False, header=False)
            
            stats = {
                'Placés': results['total_buildings'],
                'Total': total_demande,
                'Culture produite': results['total_culture_produced'],
                'Dans rayon': results['consumers_with_culture'],
                'Total consommateurs': results['total_consumers'],
                'Boost 100%': boost_stats['100%'],
                'Boost 50%': boost_stats['50%'],
                'Boost 25%': boost_stats['25%'],
                'Sans boost': boost_stats['0%']
            }
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
        
        st.download_button(
            label="📥 Télécharger les résultats",
            data=output.getvalue(),
            file_name="resultats_final.xlsx"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)