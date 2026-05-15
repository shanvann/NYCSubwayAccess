"""Load and style the NYC Subway Access layers in QGIS.

How to run:
1. Open QGIS.
2. Plugins -> Python Console (Ctrl+Alt+P).
3. Open the script in the console's editor and click Run, OR
   from the Python console:
       exec(open('/Users/shanit/projects/nyc-subway-access/qgis/load_and_style.py').read())

This script:
- Loads stations.geojson, buffers.geojson, neighborhoods.geojson from data/processed/.
- Styles neighborhoods by access_class (well-served / moderate / underserved).
- Styles buffers with light transparent fill.
- Styles stations as small circles, larger for ADA-accessible.
"""

from pathlib import Path
from qgis.core import (  # noqa: F401  (provided by QGIS runtime)
    QgsProject,
    QgsVectorLayer,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsSimpleFillSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsRuleBasedRenderer,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
)
from PyQt5.QtGui import QColor

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

CLASS_COLORS = {
    "well-served": "#2c7a3e",
    "moderate": "#e08a1a",
    "underserved": "#b62525",
}


def add_layer(path: Path, name: str) -> QgsVectorLayer:
    layer = QgsVectorLayer(str(path), name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Failed to load {path}")
    QgsProject.instance().addMapLayer(layer)
    return layer


def style_neighborhoods(layer: QgsVectorLayer) -> None:
    categories = []
    for cls, hexcolor in CLASS_COLORS.items():
        sym = QgsFillSymbol.createSimple(
            {
                "color": hexcolor,
                "outline_color": "#333333",
                "outline_width": "0.2",
                "color_alpha": "180",
            }
        )
        categories.append(QgsRendererCategory(cls, sym, cls))
    renderer = QgsCategorizedSymbolRenderer("access_class", categories)
    layer.setRenderer(renderer)
    layer.setOpacity(0.75)
    layer.triggerRepaint()


def style_buffers(layer: QgsVectorLayer) -> None:
    rules = [
        ("\"walk_min\" = 5 AND \"ada_only\" = 0", "5-min walk", "#1c64a8"),
        ("\"walk_min\" = 10 AND \"ada_only\" = 0", "10-min walk", "#6fa8d6"),
        ("\"walk_min\" = 5 AND \"ada_only\" = 1", "5-min walk (ADA)", "#7a4ca8"),
        ("\"walk_min\" = 10 AND \"ada_only\" = 1", "10-min walk (ADA)", "#b39ddb"),
    ]
    root_sym = QgsFillSymbol.createSimple({"color": "#000000"})
    root = QgsRuleBasedRenderer.Rule(root_sym)
    for expr, label, color in rules:
        sym = QgsFillSymbol.createSimple(
            {"color": color, "outline_color": color, "outline_width": "0.1"}
        )
        rule = QgsRuleBasedRenderer.Rule(sym)
        rule.setFilterExpression(expr)
        rule.setLabel(label)
        root.appendChild(rule)
    layer.setRenderer(QgsRuleBasedRenderer(root))
    layer.setOpacity(0.35)
    layer.triggerRepaint()


def style_stations(layer: QgsVectorLayer) -> None:
    rules = [
        ("\"ada\" >= 1", "ADA-accessible", "#0b6", 3.2),
        ("\"ada\" = 0", "Standard", "#222", 2.0),
    ]
    root = QgsRuleBasedRenderer.Rule(QgsMarkerSymbol.createSimple({"color": "#222"}))
    for expr, label, color, size in rules:
        sym = QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": color, "outline_color": "#fff", "outline_width": "0.3", "size": str(size)}
        )
        rule = QgsRuleBasedRenderer.Rule(sym)
        rule.setFilterExpression(expr)
        rule.setLabel(label)
        root.appendChild(rule)
    layer.setRenderer(QgsRuleBasedRenderer(root))
    layer.triggerRepaint()


def main() -> None:
    QgsProject.instance().clear()
    nbhds = add_layer(PROCESSED / "neighborhoods.geojson", "Neighborhoods (access class)")
    buffers = add_layer(PROCESSED / "buffers.geojson", "Walk buffers")
    stations = add_layer(PROCESSED / "stations.geojson", "Subway stations")
    style_neighborhoods(nbhds)
    style_buffers(buffers)
    style_stations(stations)
    iface.mapCanvas().setExtent(nbhds.extent())  # noqa: F821 — iface is provided by QGIS runtime
    iface.mapCanvas().refresh()  # noqa: F821
    print("NYC Subway Access layers loaded and styled.")


main()
