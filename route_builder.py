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
import matplotlib.pyplot as plt
import io
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle 
from datetime import datetime 

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
                formatted_coords = "{:.6f}, {:.6f}".format(
                    y, x
                )  # Formata as coordenadas
                QMessageBox.information(
                    None,
                    "Coordenadas Capturadas",
                    f"Coordenadas capturadas: {formatted_coords}",
                )
                # Copia as coordenadas para a área de transferência
                QApplication.clipboard().setText(formatted_coords)
            else:
                QMessageBox.warning(
                    None,
                    "Tipo de Geometria Inválido",
                    "Somente geometrias do tipo ponto são suportadas.",
                )


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

            # Connect the clicked signals of the folder selection buttons
            self.dlg.botaoVias.clicked.connect(self.select_via_path)
            self.dlg.botaoNos.clicked.connect(self.select_nos_path)

        result = self.dlg.exec_()
        if result:
            local = self.dlg.local_edit.text()

            if local.strip() == "":
                QMessageBox.critical(
                    None, "Error", "Please fill in the location field."
                )
                return

            if not hasattr(self, "vias_output_dir") or not hasattr(
                self, "nos_output_dir"
            ):
                QMessageBox.critical(
                    None, "Error", "Please select both vias and nos output directories."
                )
                return

            try:
                start_time = time.time()
                G = ox.graph_from_place(local, network_type="drive")

                gdf_streets = ox.graph_to_gdfs(G, nodes=False)
                gdf_nodes = ox.graph_to_gdfs(G, edges=False)

                gdf_streets = gdf_streets.applymap(
                    lambda x: x if not isinstance(x, list) else str(x)
                )
                gdf_nodes = gdf_nodes.applymap(
                    lambda x: x if not isinstance(x, list) else str(x)
                )

                via_path = self.vias_output_dir
                nos_path = self.nos_output_dir

                output_path_streets = os.path.join(
                    via_path, f"{local}_street_network.shp"
                )
                output_path_nodes = os.path.join(nos_path, f"{local}_nodes.shp")
                gdf_streets.to_file(output_path_streets)
                gdf_nodes.to_file(output_path_nodes)

                elapsed_time = time.time() - start_time

                num_nodes = len(gdf_nodes)
                num_streets = len(gdf_streets)

                self.generate_pdf_report(local, elapsed_time, num_nodes, num_streets)

                QMessageBox.information(
                    None,
                    "Success",
                    f"Street network exported as {output_path_streets} and nodes exported as {output_path_nodes}\nElapsed time: {elapsed_time:.2f} seconds",
                )

            except Exception as e:
                QMessageBox.critical(
                    None,
                    "Error",
                    f"An error occurred while extracting street network: {str(e)}",
                )
                return
            
    def generate_pdf_report(self, location, elapsed_time, num_nodes, num_streets):
        output_dir = "C:/Users/Usuario/Desktop/aa/"
        output_path = os.path.join(output_dir, "route_report.pdf")
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        centered_style = ParagraphStyle(name="Centered", alignment=1)

        story = []

        # Adicionar cabeçalho ao relatório
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S") 

        # Adicionar informações ao relatório
        report_title = Paragraph(f"<b>Route Report</b>", styles["Title"])
        story.append(report_title)
        
        # Adicionar a data como subtítulo centralizado
        report_date = Paragraph(f"<i>{current_datetime}</i>", centered_style)
        story.append(report_date)

        story.append(Spacer(1, 12))
        location_info = f"Location: {location}"
        time_info = f"Elapsed Time: {elapsed_time:.2f} seconds"
        num_nodes_info = f"Number of Nodes: {num_nodes}"
        num_street_info = f"Number of Edges: {num_streets}"
        info_paragraph = Paragraph(
            f"{location_info}<br/>{num_nodes_info}<br/>{num_street_info}<br/>{time_info}",
            styles["Normal"],
        )
        story.append(info_paragraph)

        # Adicionar o gráfico de comparação
        comparison_graph_buffer = self.plot_comparison_graph(num_nodes, num_streets)
        comparison_image = Image(comparison_graph_buffer)
        comparison_image._restrictSize(7 * inch, 6 * inch)
        story.append(comparison_image)

        doc.build(story)

        QMessageBox.information(
            None,
            "Report Generated",
            f"PDF report generated successfully at: {output_path}",
        )


    def plot_comparison_graph(self, num_nodes, num_streets):
        import matplotlib.pyplot as plt
        import io

        # Dados para o gráfico
        categories = ['Nodes', 'Streets']
        quantities = [num_nodes, num_streets]

        # Criar o gráfico de barras
        plt.bar(categories, quantities, color=['blue', 'green'])
        plt.xlabel('Categories')
        plt.ylabel('Quantity')
        plt.title('Comparison of Nodes and Streets')
        
        # Salvar o gráfico em um buffer de memória
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)

        # Limpar o gráfico para evitar sobreposições
        plt.clf()

        return buffer

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
            "Selecionar Pasta para Salvar os Nós",
            "/path/to/default/directory",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if self.nos_output_dir:
            self.dlg.nos.setText(self.nos_output_dir)
