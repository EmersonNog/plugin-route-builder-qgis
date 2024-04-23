from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QToolButton,
    QApplication,
    QWidget,
)
from qgis.core import *
from qgis.utils import iface
from qgis.gui import QgsMapTool, QgsMapToolEmitPoint, QgsMapToolIdentifyFeature

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the dialog
from .route_builder_dialog import RouteBuilderDialog
from .second_dialog import SecondDialog
import os.path
import processing
import sys, os
from osgeo import ogr
import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
import time
from shapely.geometry import LineString, Point
from osmnx.distance import nearest_nodes

class CaptureCoordinatesTool(QgsMapToolIdentifyFeature):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, e):
        features = self.identify(e.x(), e.y(), self.TopDownStopAtFirst)
        if features:
            feature = features[0].mFeature
            geometry = feature.geometry()
            if geometry.wkbType() == QgsWkbTypes.Point:
                point = geometry.asPoint()
                x = point.x()
                y = point.y()
                formatted_coords = "{:.6f}, {:.6f}".format(y, x)  # Formata as coordenadas
                QMessageBox.information(None, "Coordenadas Capturadas", f"Coordenadas capturadas: {formatted_coords}")
                # Copia as coordenadas para a área de transferência
                QApplication.clipboard().setText(formatted_coords)
            else:
                QMessageBox.warning(None, "Tipo de Geometria Inválido", "Somente geometrias do tipo ponto são suportadas.")
        
class RouteBuilder:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value("locale/userLocale")[0:2]
        locale_path = os.path.join(
            self.plugin_dir, "i18n", "RouteBuilder_{}.qm".format(locale)
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr("&Route Builder")

        self.first_start = None

    def tr(self, message):
        return QCoreApplication.translate("RouteBuilder", message)

    def run_second_part(self): 
        second_dialog = SecondDialog()
        second_dialog.exec_()


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        icon_path = ":/plugins/route_builder/icon.png"
        self.add_action(
            icon_path,
            text=self.tr("Building Networks and nodes"),
            callback=self.run,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )
        
        self.add_action(
            icon_path,
            text=self.tr("Capture Coordinates"),
            callback=self.capture_coordinates,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )

        self.add_action(
            icon_path,
            text=self.tr("Shorter Route"),
            callback=self.run_second_part,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False,
        )

        self.first_start = True

    def capture_coordinates(self):
        self.capture_tool = CaptureCoordinatesTool(self.iface.mapCanvas())
        self.iface.mapCanvas().setMapTool(self.capture_tool)

        
    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&Route Builder"), action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if self.first_start == True:
            self.first_start = False
            self.dlg = RouteBuilderDialog()

            # Conecta os sinais clicked dos botões de seleção de pasta
            self.dlg.botaoVias.clicked.connect(self.select_via_path)
            self.dlg.botaoNos.clicked.connect(self.select_nos_path)

        result = self.dlg.exec_()
        if result:
            # Extract the location name from the dialog
            local = self.dlg.local_edit.text()

            # Ensure the location is not empty
            if local.strip() == "":
                QMessageBox.critical(
                    None, "Erro", "Por favor, preencha o campo de localização."
                )
                return

            try:
                start_time = time.time()
                # Use OSMnx to download the street network data based on the location
                G = ox.graph_from_place(local, network_type="drive")

                # Convert the networkx graph to a GeoDataFrame for streets
                gdf_streets = ox.graph_to_gdfs(G, nodes=False)

                # Convert the networkx graph to a GeoDataFrame for nodes
                gdf_nodes = ox.graph_to_gdfs(G, edges=False)

                # Ensure the GeoDataFrames contain only supported field types
                gdf_streets = gdf_streets.applymap(
                    lambda x: x if not isinstance(x, list) else str(x)
                )
                gdf_nodes = gdf_nodes.applymap(
                    lambda x: x if not isinstance(x, list) else str(x)
                )

                # Get the paths from the dialog
                via_path = self.vias_output_dir
                nos_path = self.nos_output_dir

                # Export the GeoDataFrames as shapefiles for streets and nodes
                output_path_streets = os.path.join(
                    via_path, f"{local}_street_network.shp"
                )
                output_path_nodes = os.path.join(nos_path, f"{local}_nodes.shp")
                gdf_streets.to_file(output_path_streets)
                gdf_nodes.to_file(output_path_nodes)

                elapsed_time = time.time() - start_time

                QMessageBox.information(
                    None,
                    "Sucesso",
                    f"Rede de ruas exportada como {output_path_streets} e nós exportados como {output_path_nodes}\nTempo decorrido: {elapsed_time:.2f} segundos",
                )

            except Exception as e:
                QMessageBox.critical(
                    None, "Erro", f"Ocorreu um erro ao extrair a rede de ruas: {str(e)}"
                )
                return

    def select_via_path(self):
        self.vias_output_dir = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            "Selecionar Pasta para Salvar as Vias",
            "/path/to/default/directory",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if self.vias_output_dir:
            self.dlg.vias.setText(self.vias_output_dir)

    def select_nos_path(self):
        self.nos_output_dir = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            "Selecionar Pasta para Salvar os Nós",  # Alterando o título do diálogo
            "/path/to/default/directory",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if self.nos_output_dir:
            self.dlg.nos.setText(self.nos_output_dir)
