# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RouteBuilder
                                 A QGIS plugin
 "Route Builder" is a QGIS plugin that computes shortest routes on street networks using OpenStreetMap (OSM) data. Users can define a location, set origin and destination points, and calculate the shortest route between them.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2024-04-19
        copyright            : (C) 2024 by Nogueira
        email                : catce.nogueira@gmail.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load RouteBuilder class from file RouteBuilder.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .route_builder import RouteBuilder
    return RouteBuilder(iface)