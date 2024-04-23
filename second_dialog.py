from PyQt5.QtWidgets import QDialog, QLineEdit, QMessageBox
import osmnx as ox
import networkx as nx
from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsProject
from shapely.geometry import Point, LineString
from .create_route_dialog_base import CreateRouteDialog

class SecondDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.ui = CreateRouteDialog()
        self.ui.setupUi(self)
        self.setWindowTitle("Builder Router")

        # Referencing the QLineEdit widgets
        self.lineEditLocal = self.ui.local
        self.lineEditOrigem = self.ui.origem
        self.lineEditDestino = self.ui.destino

        # Connect the button clicked event to a method
        self.ui.buscar.clicked.connect(self.buscar_redes_e_calcular_rota)

    def buscar_redes_e_calcular_rota(self):
        # Get the location input
        location = self.lineEditLocal.text()

        # Fetch road networks and nodes using OSMnx
        try:
            G = ox.graph_from_place(location, network_type='drive')
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch road networks: {str(e)}")
            return

        # Get origin and destination points from QLineEdit widgets
        origem_text = self.lineEditOrigem.text()
        destino_text = self.lineEditDestino.text()

        # Convert origin and destination text to Points
        origem = Point(float(origem_text.split(',')[0]), float(origem_text.split(',')[1]))
        destino = Point(float(destino_text.split(',')[0]), float(destino_text.split(',')[1]))

        # Find the nearest nodes to the origin and destination
        origem_node = self.find_nearest_node(G, origem)
        destino_node = self.find_nearest_node(G, destino)

        # Calculate the shortest path using A* algorithm
        try:
            shortest_path = nx.astar_path(G, origem_node, destino_node, heuristic=lambda u, v: self.distance_heuristic(G, u, v))

            # Retrieve the geometry of the route
            route_nodes = [G.nodes[node] for node in shortest_path]
            route_line = LineString([(node['x'], node['y']) for node in route_nodes])

            # Convert Shapely LineString to QgsGeometry
            route_geometry = QgsGeometry.fromPolylineXY([QgsPointXY(point[0], point[1]) for point in route_line.coords])

            # Create a QgsVectorLayer from the route geometry
            route_layer = QgsVectorLayer("LineString", "route_temp", "memory")
            provider = route_layer.dataProvider()
            features = [QgsFeature()]
            features[0].setGeometry(route_geometry)
            provider.addFeatures(features)

            # Add the layer to the QGIS project
            QgsProject.instance().addMapLayer(route_layer)

            QMessageBox.information(self, "Success", "Route line added as a temporary layer in QGIS")
        except nx.NetworkXNoPath:
            QMessageBox.critical(self, "Error", "No path found between the origin and destination.")

    def find_nearest_node(self, G, point):
        nearest_node = None
        nearest_distance = float('inf')
        for node in G.nodes():
            distance = point.distance(Point(G.nodes[node]['y'], G.nodes[node]['x']))
            if distance < nearest_distance:
                nearest_node = node
                nearest_distance = distance
        return nearest_node

    def distance_heuristic(self, G, u, v):
        """Heuristic function for A* algorithm."""
        # Assuming Euclidean distance as the heuristic
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        return ((u_data['x'] - v_data['x'])**2 + (u_data['y'] - v_data['y'])**2)**0.5
