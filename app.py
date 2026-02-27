"""Application Streamlit pour placement de bâtiments"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import sys
import io

print("=== DÉBUT DES LOGS STREAMLIT ===")
print(f"Python version: {sys.version}")
print(f"Streamlit version: {st.__version__}")
print("Configuration de la page...")

# Configuration de la page
st.set_page_config(
    page_title="Optimiseur de Bâtiments",
    page_icon="🏗️",
    layout="wide"
)

print("Page configurée avec succès")

# Titre principal
st.title("🏗️ Optimiseur de Placement de Bâtiments")

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
    
    # Afficher un exemple
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

elif uploaded_file and optimize_button:
    try:
        with st.spinner("Lecture du fichier..."):
            # Lire les données
            df_terrain = pd.read_excel(uploaded_file, sheet_name=0, header=None)
            df_buildings = pd.read_excel(uploaded_file, sheet_name=1)
            
        st.success(f"Fichier chargé avec succès!")
        st.write(f"Terrain: {df_terrain.shape[0]}x{df_terrain.shape[1]} cases")
        st.write(f"Bâtiments: {len(df_buildings)} types")
        
        # Aperçu
        st.subheader("Aperçu des données")
        tab1, tab2 = st.tabs(["Terrain", "Bâtiments"])
        
        with tab1:
            st.dataframe(df_terrain)
        with tab2:
            st.dataframe(df_buildings)
            
        st.info("🔧 L'algorithme d'optimisation va maintenant s'exécuter...")
        
    except Exception as e:
        st.error(f"Erreur: {str(e)}")
        print(f"ERREUR: {str(e)}")

print("=== FIN DU CODE ===")