### Absolute imports
import json
import tempfile

import pandas as pd
import streamlit as st
import streamlit_analytics

from modules.data_loader import (
    fetch_data_BigQuery,
    fetch_data_gouv,
    fetch_summarized_data,
)
from modules.GUI.plotter import Plotter

### Relative imports
from ..config import (
    azure_credentials,
    bigquery_credentials,
    data_URL,
    firebase_credentials,
    page_config,
)
from .ui_components import display_sidebar, init_page_config, init_session_state

firebase_cred = firebase_credentials()
azure_cred = azure_credentials()
bigquery_cred = bigquery_credentials()
data_sources_origin = data_URL()

if firebase_cred:
    ### Secure way to store the firestore keys and provide them to start_tracking
    tfile = tempfile.NamedTemporaryFile(mode="w+")
    json.dump(firebase_cred, tfile)
    tfile.flush()
    streamlit_analytics.start_tracking(
        firestore_key_file=tfile.name, firestore_collection_name="sotisimmo_analytics"
    )
else:
    print("No credentials were found. Analytics will not be tracked.")


### App
class App(Plotter):
    """
    This class creates a Streamlit app that displays the average price of real estate properties in France, by department.
    """

    def __init__(self):
        print("Init the app...")

        # init_page_config(page_config)
        init_session_state()

        st.markdown(page_config().get("markdown"), unsafe_allow_html=True)

        self.data_loaded = True  # Variable to check if the data has been loaded
        self.properties_summarized = fetch_summarized_data()

        with st.sidebar:
            display_sidebar(page_config)
            self.initial_request()

        if isinstance(self.properties_input, pd.DataFrame):
            if self.local_types:
                self.create_plots()
            else:
                st.sidebar.error(
                    "Pas d'information disponible pour le département {} en {}. Sélectionnez une autre configuration.".format(
                        self.selected_department, self.selected_year
                    )
                )

    def initial_request(self):
        """
        Load data from the French open data portal and initialize the parameters of the app.

        Parameters
        ----------
        None

        Returns
        -------
        self.properties_input: Pandas dataframe
            The dataframe containing the data loaded from the French open data portal.
        self.selected_department: str
            The department selected by the user.
        self.selected_year: str
            The year selected by the user.
        self.selected_local_type: str
            The property type selected by the user.
        self.selected_mapbox_style: str
            The map style selected by the user.
        self.selected_colormap: str
            The colormap selected by the user.
        """

        ### Set up the department selectbox
        departments = [str(i).zfill(2) for i in range(1, 96)]
        departments.remove("20")
        departments.extend(["971", "972", "973", "974", "2A", "2B"])
        default_dept = departments.index("06")
        self.selected_department = st.selectbox(
            "Département", departments, index=default_dept
        )

        # Check if the department has changed and reset the session state for the postcode if needed
        if (
            "previous_selected_department" in st.session_state
            and st.session_state.previous_selected_department
            != self.selected_department
        ):
            if "selected_postcode_title" in st.session_state:
                del st.session_state.selected_postcode_title
            if "selected_postcode" in st.session_state:
                del st.session_state.selected_postcode

        # Update the previous selected department in the session state
        st.session_state.previous_selected_department = self.selected_department

        ### Set up the year selectbox
        years_range = data_sources_origin.get("available_years_datagouv")
        years = [f"Vendus en {year}" for year in years_range]
        default_year = years.index("Vendus en 2023")

        # if True: # Tests
        #     years.extend(['En vente 2024'])
        #     default_year = years.index('En vente 2024')

        self.selected_year = st.selectbox("Année", years, index=default_year).split(
            " "
        )[-1]

        ### Load data
        if "2024" not in self.selected_year:
            self.properties_input = fetch_data_gouv(
                self.selected_department, self.selected_year
            )
        else:
            self.properties_input = fetch_data_BigQuery(
                bigquery_cred, self.selected_department
            )

        if not self.properties_input is None:
            ### Set up a copy of the dataframe
            self.properties_input = self.properties_input.copy()

            ### Set up the property type selectbox
            self.local_types = sorted(self.properties_input["type_local"].unique())
            selectbox_key = (
                f"local_type_{self.selected_department}_{self.selected_year}"
            )
            self.selected_local_type = st.selectbox(
                "Type de bien", self.local_types, key=selectbox_key
            )

            ### Set up the normalization checkbox
            self.normalize_by_area = st.checkbox("Prix au m²", True)

            if self.normalize_by_area:
                self.properties_input["valeur_fonciere"] = (
                    (
                        self.properties_input["valeur_fonciere"]
                        / self.properties_input["surface_reelle_bati"]
                    )
                    .round()
                    .astype(int)
                )

            # Ajoutez ceci après les autres éléments dans la barre latérale
            self.selected_plots = st.multiselect(
                "Supprimer ou ajouter des graphiques",
                ["Carte", "Fig. 1", "Fig. 2", "Fig. 3", "Fig. 4"],
                ["Carte", "Fig. 1", "Fig. 2", "Fig. 3", "Fig. 4"],
            )

            ### Set up the chatbot
            st.divider()
            with st.expander("Chatbot (Optionnel)"):
                self.chatbot_checkbox = st.checkbox("Activer le chat bot", False)
                self.selected_model = st.selectbox(
                    "Modèle",
                    ["GPT 3.5", "GPT 4", "Llama2-7B", "Llama2-13B", "Mistral"],
                    index=1,
                )
                self.model_api_key = st.text_input(
                    "Entrez une clé API 🔑",
                    type="password",
                    help="Trouvez votre clé [OpenAI](https://platform.openai.com/account/api-keys) ou [Replicate](https://replicate.com/account/api-tokens).",
                )
                st.info(
                    "ℹ️ Votre clé API n'est pas conservée. Elle sera automatiquement supprimée lorsque vous fermerez ou rechargerez cette page."
                )

                if self.chatbot_checkbox:
                    if "GPT" in self.selected_model:
                        if not self.model_api_key:
                            st.warning("⚠️ Entrez une clé API **Open AI**.")
                    else:
                        # st.warning('⚠️ Entrez une clé API **Repliacte**.')
                        st.error(
                            "⚠️ Ce modèle n'est pas encore disponible. Veuillez utiliser GPT."
                        )
                    # st.stop()

                # st.markdown('Pour obtenir une clé API, rendez-vous sur le site de [openAI](https://platform.openai.com/api-keys).')


if firebase_cred:
    streamlit_analytics.stop_tracking(
        firestore_key_file=tfile.name, firestore_collection_name="sotisimmo_analytics"
    )

if __name__ == "__main__":
    App()