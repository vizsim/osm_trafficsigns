"""Generate the QGIS style file (`output/signs.qml`) for traffic-sign parquets.

The renderer stacks up to ``MAX_LAYERS`` SVG markers per feature, one per code
in ``sign_list``, centered vertically on the point geometry. Codes whose SVG
isn't on disk (e.g. bracketed free-text annotations like ``[Lieferverkehr
frei]``) render at size 0 and show up as a fallback text label instead.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

MAX_LAYERS = 4
SIGN_SIZE_MM = 8.0
ROOT = "//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns"

# Resolved at runtime in QGIS as either @project_folder or the absolute path.
ROOT_EXPR = f"coalesce(nullif(@project_folder, ''), '{ROOT}')"


def svg_path_expr(index: int) -> str:
    """Path to the N-th SVG: ``<root>/symbols/<country>/<sign_list[N]>.svg``."""
    return (
        f"with_variable('root', {ROOT_EXPR},"
        f" @root || '/symbols/' || \"country_code\" || '/' ||"
        f" trim(array_get(string_to_array(\"sign_list\", ','), {index}))"
        f" || '.svg')"
    )


def size_expr(index: int) -> str:
    """0 if SVG missing (gates visibility), else SIGN_SIZE_MM."""
    return f"if(file_exists({svg_path_expr(index)}), {SIGN_SIZE_MM}, 0)"


def offset_expr(index: int) -> str:
    """Stack centered on point. Positive Y = down, so sign 0 = top."""
    return (
        f"'0,' || (({index} -"
        f" (array_length(string_to_array(\"sign_list\", ',')) - 1) / 2.0)"
        f" * {SIGN_SIZE_MM})"
    )


def label_expr() -> str:
    """Show codes whose SVGs don't exist (newline-joined). Empty if all rendered."""
    inner = (
        f"@root || '/symbols/' || \"country_code\" || '/' ||"
        f" trim(@element) || '.svg'"
    )
    return (
        f"with_variable('root', {ROOT_EXPR},"
        f" array_to_string(array_filter("
        f" string_to_array(\"sign_list\", ','),"
        f" not file_exists({inner})"
        f"), '\\n'))"
    )


def layer_xml(index: int) -> str:
    name = escape(svg_path_expr(index), quote=True)
    size = escape(size_expr(index), quote=True)
    offset = escape(offset_expr(index), quote=True)
    return f"""        <layer pass="0" enabled="1" class="SvgMarker" locked="0">
          <Option type="Map">
            <Option name="angle" type="QString" value="0"/>
            <Option name="color" type="QString" value="0,0,0,255"/>
            <Option name="fixedAspectRatio" type="QString" value="0"/>
            <Option name="horizontal_anchor_point" type="QString" value="1"/>
            <Option name="name" type="QString" value=""/>
            <Option name="offset" type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit" type="QString" value="MM"/>
            <Option name="outline_color" type="QString" value="0,0,0,255"/>
            <Option name="outline_width" type="QString" value="0"/>
            <Option name="outline_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="outline_width_unit" type="QString" value="MM"/>
            <Option name="parameters" type="Map"/>
            <Option name="scale_method" type="QString" value="diameter"/>
            <Option name="size" type="QString" value="{SIGN_SIZE_MM}"/>
            <Option name="size_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="size_unit" type="QString" value="MM"/>
            <Option name="vertical_anchor_point" type="QString" value="1"/>
          </Option>
          <data_defined_properties>
            <Option type="Map">
              <Option name="name" type="QString" value=""/>
              <Option name="properties" type="Map">
                <Option name="name" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="{name}"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="size" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="{size}"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="offset" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="{offset}"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="angle" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="coalesce(&quot;direction&quot;, 0)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
              </Option>
              <Option name="type" type="QString" value="collection"/>
            </Option>
          </data_defined_properties>
        </layer>"""


def build_qml() -> str:
    layers = "\n".join(layer_xml(i) for i in range(MAX_LAYERS))
    label = escape(label_expr(), quote=True)
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0-Prizren" styleCategories="Symbology|Labeling|Rendering">
  <renderer-v2 type="singleSymbol" enableorderby="0" referencescale="-1" forceraster="0" symbollevels="0">
    <symbols>
      <symbol type="marker" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <data_defined_properties>
          <Option type="Map">
            <Option name="name" type="QString" value=""/>
            <Option name="properties" type="Map"/>
            <Option name="type" type="QString" value="collection"/>
          </Option>
        </data_defined_properties>
{layers}
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="8" fontFamily="Sans" textColor="50,50,50,255" fontWeight="50" fontItalic="0" fontUnderline="0" fontStrikeout="0" fieldName="{label}" isExpression="1" textOpacity="1" allowHtml="0" fontKerning="1" fontLetterSpacing="0" fontWordSpacing="0" multilineHeight="1.1" capitalization="0" useSubstitutions="0" forcedBold="0" forcedItalic="0" namedStyle="Regular" blendMode="0"/>
      <text-buffer bufferDraw="1" bufferSize="0.8" bufferColor="255,255,255,230" bufferSizeUnits="MM" bufferOpacity="1" bufferJoinStyle="64" bufferNoFill="0"/>
      <placement placement="1" dist="2" distUnits="MM" priority="5" placementFlags="10" xOffset="0" yOffset="0"/>
      <rendering scaleVisibility="1" scaleMin="1" scaleMax="50000" obstacle="1" obstacleType="0" displayAll="0" mergeLines="0" minFeatureSize="0" fontLimitPixelSize="0" fontMinPixelSize="3" fontMaxPixelSize="10000"/>
    </settings>
  </labeling>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
</qgis>
"""


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    qml = build_qml()
    for name in ("signs.qml", "bremen_signs.qml"):
        (out_dir / name).write_text(qml)
        print(f"wrote {out_dir / name}")


if __name__ == "__main__":
    main()
