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

print("=== DÉMARRAGE DE L'APPLICATION ===")

@dataclass
class Building:
    """Classe représentant un bâtiment"""
    name: str
    length: int
    width: int
    quantity: int
    culture_produced: float  # Culture que ce bâtiment PRODUIT (pour booster les autres)
    radius: int  # Rayon de propagation de sa culture
    boost_25: float  # Seuil pour être boosté à 25%
    boost_50: float  # Seuil pour être boosté à 50%
    boost_100: float  # Seuil pour être boosté à 100%
    
    def get_dimensions(self, orientation: str) -> Tuple[int, int]:
        if orientation == 'H':
            return self.length, self.width
        else:
            return self.width, self.length
    
    def is_producer(self) -> bool:
        """Vérifie si ce bâtiment produit de la culture (pour booster les autres)"""
        return self.culture_produced > 0 and self.radius > 0
    
    def can_be_boosted(self) -> bool:
        """Vérifie si ce bâtiment peut être boosté (a des seuils de boost)"""
        return (self.boost_25 > 0 or self.boost_50 > 0 or self.boost_100 > 0)

class BuildingPlacer:
    """Classe principale pour le placement des bâtiments"""
    
    def __init__(self, terrain_grid: np.ndarray, buildings: List[Building]):
        self.terrain_grid = terrain_grid
        self.buildings = buildings
        self.placement_grid = None
        self.placed_buildings = []
        self.available_zones = []
        self.initialize_grids()
        
    def initialize_grids(self):
        """Initialise les grilles avec convention: 1=libre, 0=obstrué"""
        self.placement_grid = np.zeros_like(self.terrain_grid)
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
    
    def can_place_in_zone(self, zone: List[Tuple[int, int]], x: int, y: int, 
                          length: int, width: int) -> bool:
        """Vérifie si un bâtiment peut être placé dans une zone"""
        zone_set = set(zone)
        for i in range(length):
            for j in range(width):
                if (x + i, y + j) not in zone_set:
                    return False
        return True
    
    def calculate_culture_in_radius(self, x: int, y: int, length: int, width: int, 
                                   radius: int) -> Tuple[float, List[str]]:
        """
        Calcule la quantité totale de culture produite dans le rayon donné
        ET retourne la liste des bâtiments qui fournissent cette culture
        """
        total_culture = 0
        source_buildings = []
        center_x = x + length // 2
        center_y = y + width // 2
        
        # Parcourir toutes les cases dans le rayon
        for i in range(max(0, center_x - radius), 
                      min(self.placement_grid.shape[0], center_x + radius + 1)):
            for j in range(max(0, center_y - radius),
                          min(self.placement_grid.shape[1], center_y + radius + 1)):
                cell_value = self.placement_grid[i, j]
                # Vérifier que c'est bien un bâtiment placé ( > 0)
                if cell_value > 0:
                    # Vérifier que l'indice est valide
                    building_idx = cell_value - 1
                    if 0 <= building_idx < len(self.placed_buildings):
                        placed = self.placed_buildings[building_idx]
                        if placed['building'].is_producer():
                            total_culture += placed['building'].culture_produced
                            if placed['building'].name not in source_buildings:
                                source_buildings.append(placed['building'].name)
        
        return total_culture, source_buildings
    
    def calculate_boost_for_building(self, building: Building, x: int, y: int, 
                                    length: int, width: int) -> Tuple[float, float, List[str]]:
        """
        Calcule le boost reçu par un bâtiment basé sur la culture dans son rayon
        Retourne: (boost, culture_recue, liste_des_sources)
        """
        if not building.can_be_boosted():
            return 1.0, 0, []
        
        total_culture, sources = self.calculate_culture_in_radius(x, y, length, width, building.radius)
        
        if total_culture >= building.boost_100:
            return 2.0, total_culture, sources
        elif total_culture >= building.boost_50:
            return 1.5, total_culture, sources
        elif total_culture >= building.boost_25:
            return 1.25, total_culture, sources
        else:
            return 1.0, total_culture, sources
    
    def place_building(self, building: Building, x: int, y: int, orientation: str) -> bool:
        """Place un bâtiment"""
        length, width = building.get_dimensions(orientation)
        
        building_id = len(self.placed_buildings) + 1
        for i in range(length):
            for j in range(width):
                self.placement_grid[x + i, y + j] = building_id
        
        # Calculer le boost initial (basé sur les bâtiments déjà placés)
        initial_boost, culture_recue, sources = self.calculate_boost_for_building(building, x, y, length, width)
        
        placed_info = {
            'building': building,
            'x': x, 'y': y,
            'orientation': orientation,
            'length': length,
            'width': width,
            'building_id': building_id,
            'initial_boost': initial_boost,
            'culture_recue': culture_recue,
            'sources_boost': sources
        }
        self.placed_buildings.append(placed_info)
        return True
    
    def calculate_final_production(self) -> Tuple[float, dict, List[dict]]:
        """
        Calcule la production finale avec tous les boosts
        Retourne aussi les détails de culture reçue pour chaque bâtiment
        """
        total_production = 0
        boost_stats = {'100%': 0, '50%': 0, '25%': 0, '0%': 0}
        boost_details = []
        
        # Recalculer tous les boosts maintenant que tous les bâtiments sont placés
        for placed in self.placed_buildings:
            building = placed['building']
            
            if building.can_be_boosted():
                boost, culture_recue, sources = self.calculate_boost_for_building(
                    building, placed['x'], placed['y'],
                    placed['length'], placed['width']
                )
            else:
                boost, culture_recue, sources = 1.0, 0, []
            
            placed['final_boost'] = boost
            placed['final_culture_recue'] = culture_recue
            placed['final_sources'] = sources
            
            # Seuls les producteurs contribuent à la production totale
            if building.is_producer():
                production = building.culture_produced
                total_production += production
            
            # Statistiques des boosts (seulement pour les bâtiments qui peuvent être boostés)
            if building.can_be_boosted():
                if boost >= 2.0:
                    boost_stats['100%'] += 1
                elif boost >= 1.5:
                    boost_stats['50%'] += 1
                elif boost >= 1.25:
                    boost_stats['25%'] += 1
                else:
                    boost_stats['0%'] += 1
                
                # Détail pour ce bâtiment
                boost_details.append({
                    'nom': building.name,
                    'boost': boost,
                    'culture_recue': culture_recue,
                    'sources': ', '.join(sources) if sources else 'aucune',
                    'seuil_25': building.boost_25,
                    'seuil_50': building.boost_50,
                    'seuil_100': building.boost_100
                })
        
        return total_production, boost_stats, boost_details
    
    def find_best_placement_for_producer(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve le meilleur placement pour un producteur (pour maximiser sa couverture)"""
        best_score = -1
        best_placement = None
        
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
                        # Pour un producteur, on veut maximiser le nombre de futurs bâtiments dans son rayon
                        # Pour l'instant, on prend une position centrale
                        center_x = (min_x + max_x) // 2
                        center_y = (min_y + max_y) // 2
                        dist = abs(x + length//2 - center_x) + abs(y + width//2 - center_y)
                        score = -dist  # Plus proche du centre = mieux
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {'x': x, 'y': y, 'orientation': orientation}
        
        return best_placement
    
    def find_best_placement_for_consumer(self, building: Building, zone: List[Tuple[int, int]]) -> Optional[dict]:
        """Trouve le meilleur placement pour un consommateur (pour maximiser son boost)"""
        best_score = -1
        best_placement = None
        
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
                        # Calculer le boost potentiel basé sur les producteurs déjà placés
                        boost, culture_recue, sources = self.calculate_boost_for_building(building, x, y, length, width)
                        
                        # Bonus si proche d'autres consommateurs (pour futurs boosts)
                        proximity_bonus = 0
                        center_x = x + length//2
                        center_y = y + width//2
                        
                        for placed in self.placed_buildings:
                            if placed['building'].can_be_boosted():
                                p_center_x = placed['x'] + placed['length']//2
                                p_center_y = placed['y'] + placed['width']//2
                                dist = abs(center_x - p_center_x) + abs(center_y - p_center_y)
                                if dist <= building.radius:
                                    proximity_bonus += 10
                        
                        score = boost * 100 + proximity_bonus + culture_recue
                        
                        if score > best_score:
                            best_score = score
                            best_placement = {
                                'x': x, 'y': y, 'orientation': orientation, 
                                'boost': boost, 'culture_recue': culture_recue
                            }
        
        return best_placement
    
    def place_all_buildings(self) -> dict:
        """Place tous les bâtiments en optimisant les boosts"""
        self.initialize_grids()
        self.placed_buildings = []
        
        total_to_place = sum(b.quantity for b in self.buildings)
        
        # Séparer les producteurs et les consommateurs
        producers = []
        consumers = []
        for building in self.buildings:
            for _ in range(building.quantity):
                if building.is_producer():
                    producers.append(building)
                else:
                    consumers.append(building)
        
        st.info(f"🎯 {len(producers)} producteurs de culture, {len(consumers)} consommateurs")
        
        # Trier les producteurs par culture produite (du plus grand au plus petit)
        producers.sort(key=lambda b: -b.culture_produced)
        
        # Trier les consommateurs par seuils de boost (les plus faciles à booster d'abord)
        consumers.sort(key=lambda b: (b.boost_25 if b.boost_25 > 0 else 9999, 
                                     b.boost_50 if b.boost_50 > 0 else 9999, 
                                     b.boost_100 if b.boost_100 > 0 else 9999))
        
        # Identifier les zones
        self.find_available_zones()
        initial_free = np.sum(self.placement_grid == 0)
        
        # Phase 1: Placer les producteurs au centre des grandes zones
        self.available_zones.sort(key=len, reverse=True)
        
        for producer in producers[:]:
            if not self.available_zones:
                break
                
            # Prendre la plus grande zone
            zone = self.available_zones[0]
            placement = self.find_best_placement_for_producer(producer, zone)
            
            if placement:
                self.place_building(producer, placement['x'], placement['y'], placement['orientation'])
                producers.remove(producer)
                
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
        
        # Phase 2: Placer les consommateurs autour des producteurs
        all_consumers = consumers[:]
        for consumer in all_consumers:
            best_placement = None
            best_score = -1
            best_zone_idx = -1
            
            for zone_idx, zone in enumerate(self.available_zones):
                # Vérifier si le bâtiment peut rentrer dans la zone
                area = consumer.get_dimensions('H')[0] * consumer.get_dimensions('H')[1]
                if area <= len(zone):
                    placement = self.find_best_placement_for_consumer(consumer, zone)
                    if placement and placement.get('boost', 0) > best_score:
                        best_score = placement['boost']
                        best_placement = placement
                        best_zone_idx = zone_idx
            
            if best_placement:
                self.place_building(consumer, best_placement['x'], best_placement['y'], 
                                  best_placement['orientation'])
                consumers.remove(consumer)
                
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
        
        # Phase 3: Placer les bâtiments restants (producteurs non placés, consommateurs restants)
        remaining = producers + consumers
        for building in remaining:
            placed = False
            for zone_idx, zone in enumerate(self.available_zones):
                if placed:
                    break
                for orientation in ['H', 'V']:
                    if placed:
                        break
                    length, width = building.get_dimensions(orientation)
                    
                    # Vérifier si le bâtiment peut rentrer dans la zone
                    if length > (max(p[0] for p in zone) - min(p[0] for p in zone) + 1) or \
                       width > (max(p[1] for p in zone) - min(p[1] for p in zone) + 1):
                        continue
                    
                    for x in range(min(p[0] for p in zone), max(p[0] for p in zone) - length + 2):
                        if placed:
                            break
                        for y in range(min(p[1] for p in zone), max(p[1] for p in zone) - width + 2):
                            if self.can_place_in_zone(zone, x, y, length, width):
                                self.place_building(building, x, y, orientation)
                                placed = True
                                break
        
        # Calculer la production finale
        total_production, boost_stats, boost_details = self.calculate_final_production()
        
        return {
            'total_production': total_production,
            'buildings_placed': len(self.placed_buildings),
            'buildings_total': total_to_place,
            'grid': self.placement_grid.copy(),
            'placed_buildings': copy.deepcopy(self.placed_buildings),
            'boost_stats': boost_stats,
            'boost_details': boost_details,
            'producers_placed': len([p for p in self.placed_buildings if p['building'].is_producer()]),
            'consumers_placed': len([p for p in self.placed_buildings if not p['building'].is_producer()]),
            'initial_free': initial_free,
            'occupied': np.sum(self.placement_grid > 0),
            'free': np.sum(self.placement_grid == 0),
            'obstructed': np.sum(self.placement_grid == -1)
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
st.set_page_config(page_title="Optimiseur de Bâtiments", page_icon="🏗️", layout="wide")

st.title("🏗️ Optimiseur de Placement de Bâtiments")
st.markdown("""
**Configuration :**
- **Bâtiments producteurs** (avec culture > 0 et rayonnement > 0) : produisent de la culture pour booster les autres
- **Bâtiments consommateurs** (avec seuils de boost) : peuvent être boostés par les producteurs

Les résultats montrent pour chaque bâtiment la **culture reçue** des producteurs environnants.
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
        
        # Afficher les colonnes pour debug
        with st.expander("📋 Colonnes trouvées"):
            st.write(list(df_buildings.columns))
        
        # Création des bâtiments
        buildings = []
        for _, row in df_buildings.iterrows():
            # Fonction pour récupérer les valeurs en gérant les NaN
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
        
        # Compter les producteurs et consommateurs
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
            st.metric("🏢 Placés", f"{results['buildings_placed']}/{total_demande}")
        with col2:
            st.metric("💰 Production", f"{results['total_production']:.0f}")
        with col3:
            util = results['occupied'] / cells_libres * 100 if cells_libres > 0 else 0
            st.metric("📊 Utilisation", f"{util:.1f}%")
        with col4:
            st.metric("🎯 Producteurs", f"{results['producers_placed']}")
        
        # Statistiques des boosts
        if results['boost_details']:
            st.subheader("⚡ Détail des boosts par bâtiment")
            
            # Créer un DataFrame pour les détails
            df_boosts = pd.DataFrame(results['boost_details'])
            df_boosts.columns = ['Bâtiment', 'Boost', 'Culture reçue', 'Sources', 'Seuil 25%', 'Seuil 50%', 'Seuil 100%']
            
            # Formatage
            df_boosts['Boost'] = df_boosts['Boost'].apply(lambda x: f"{x:.2f}x")
            df_boosts['Culture reçue'] = df_boosts['Culture reçue'].apply(lambda x: f"{x:.0f}")
            
            st.dataframe(df_boosts, use_container_width=True)
            
            # Graphique de distribution
            st.subheader("📊 Distribution des boosts")
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
            
            fig_boost = go.Figure(data=[
                go.Bar(x=['100%', '50%', '25%', '0%'],
                      y=[boost_stats['100%'], boost_stats['50%'], 
                         boost_stats['25%'], boost_stats['0%']],
                      text=[f"{boost_stats['100%']}", f"{boost_stats['50%']}", 
                            f"{boost_stats['25%']}", f"{boost_stats['0%']}"],
                      textposition='auto')
            ])
            fig_boost.update_layout(height=400, title="Distribution des boosts")
            st.plotly_chart(fig_boost, use_container_width=True)
            
        else:
            st.info("ℹ️ Aucun bâtiment boostable n'a été placé - les seuils sont peut-être trop élevés")
        
        # Visualisation
        st.subheader("🗺️ Carte de placement")
        fig = create_heatmap(results['grid'], "Placement")
        st.plotly_chart(fig, use_container_width=True)
        
        # Export
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Placements
            placement_data = []
            for p in results['placed_buildings']:
                placement_data.append({
                    'Bâtiment': p['building'].name,
                    'Type': 'Producteur' if p['building'].is_producer() else 'Consommateur',
                    'X': p['x'], 'Y': p['y'],
                    'Orientation': p['orientation'],
                    'Boost final': p.get('final_boost', 1.0),
                    'Culture reçue': p.get('final_culture_recue', 0),
                    'Sources': ', '.join(p.get('final_sources', [])) if p.get('final_sources') else ''
                })
            pd.DataFrame(placement_data).to_excel(writer, sheet_name='Placements', index=False)
            
            # Grille
            pd.DataFrame(results['grid']).to_excel(writer, sheet_name='Grille', index=False, header=False)
            
            # Stats
            stats = {
                'Placés': results['buildings_placed'],
                'Total': total_demande,
                'Production': results['total_production'],
                'Producteurs': results['producers_placed'],
                'Consommateurs': results['consumers_placed']
            }
            stats.update(results['boost_stats'])
            pd.DataFrame([stats]).to_excel(writer, sheet_name='Statistiques', index=False)
            
            # Détail des boosts (si disponible)
            if results['boost_details']:
                pd.DataFrame(results['boost_details']).to_excel(writer, sheet_name='Details_Boosts', index=False)
        
        st.download_button("📥 Télécharger les résultats", data=output.getvalue(), 
                          file_name="resultats_avec_culture_recue.xlsx")
        
    except Exception as e:
        st.error(f"❌ Erreur: {str(e)}")
        st.exception(e)