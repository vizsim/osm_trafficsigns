<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
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
        <layer pass="0" enabled="1" class="SvgMarker" locked="0">
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
            <Option name="size" type="QString" value="8.0"/>
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
                  <Option name="expression" type="QString" value="with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 0)) || &#x27;.svg&#x27;)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="size" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="if(file_exists(with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 0)) || &#x27;.svg&#x27;)), 8.0, 0)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="offset" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="&#x27;0,&#x27; || ((0 - (array_length(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;)) - 1) / 2.0) * 8.0)"/>
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
        </layer>
        <layer pass="0" enabled="1" class="SvgMarker" locked="0">
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
            <Option name="size" type="QString" value="8.0"/>
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
                  <Option name="expression" type="QString" value="with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 1)) || &#x27;.svg&#x27;)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="size" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="if(file_exists(with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 1)) || &#x27;.svg&#x27;)), 8.0, 0)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="offset" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="&#x27;0,&#x27; || ((1 - (array_length(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;)) - 1) / 2.0) * 8.0)"/>
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
        </layer>
        <layer pass="0" enabled="1" class="SvgMarker" locked="0">
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
            <Option name="size" type="QString" value="8.0"/>
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
                  <Option name="expression" type="QString" value="with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 2)) || &#x27;.svg&#x27;)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="size" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="if(file_exists(with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 2)) || &#x27;.svg&#x27;)), 8.0, 0)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="offset" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="&#x27;0,&#x27; || ((2 - (array_length(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;)) - 1) / 2.0) * 8.0)"/>
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
        </layer>
        <layer pass="0" enabled="1" class="SvgMarker" locked="0">
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
            <Option name="size" type="QString" value="8.0"/>
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
                  <Option name="expression" type="QString" value="with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 3)) || &#x27;.svg&#x27;)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="size" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="if(file_exists(with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), @root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(array_get(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), 3)) || &#x27;.svg&#x27;)), 8.0, 0)"/>
                  <Option name="type" type="int" value="3"/>
                </Option>
                <Option name="offset" type="Map">
                  <Option name="active" type="bool" value="true"/>
                  <Option name="expression" type="QString" value="&#x27;0,&#x27; || ((3 - (array_length(string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;)) - 1) / 2.0) * 8.0)"/>
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
        </layer>
      </symbol>
    </symbols>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontSize="8" fontFamily="Sans" textColor="50,50,50,255" fontWeight="50" fontItalic="0" fontUnderline="0" fontStrikeout="0" fieldName="with_variable(&#x27;root&#x27;, coalesce(nullif(@project_folder, &#x27;&#x27;), &#x27;//wsl.localhost/Ubuntu/home/simon/osm_trafficsigns&#x27;), array_to_string(array_filter( string_to_array(&quot;sign_list&quot;, &#x27;,&#x27;), not file_exists(@root || &#x27;/viz/symbols/&#x27; || &quot;country_code&quot; || &#x27;/&#x27; || trim(@element) || &#x27;.svg&#x27;)), &#x27;\n&#x27;))" isExpression="1" textOpacity="1" allowHtml="0" fontKerning="1" fontLetterSpacing="0" fontWordSpacing="0" multilineHeight="1.1" capitalization="0" useSubstitutions="0" forcedBold="0" forcedItalic="0" namedStyle="Regular" blendMode="0"/>
      <text-buffer bufferDraw="1" bufferSize="0.8" bufferColor="255,255,255,230" bufferSizeUnits="MM" bufferOpacity="1" bufferJoinStyle="64" bufferNoFill="0"/>
      <placement placement="1" dist="2" distUnits="MM" priority="5" placementFlags="10" xOffset="0" yOffset="0"/>
      <rendering scaleVisibility="1" scaleMin="1" scaleMax="50000" obstacle="1" obstacleType="0" displayAll="0" mergeLines="0" minFeatureSize="0" fontLimitPixelSize="0" fontMinPixelSize="3" fontMaxPixelSize="10000"/>
    </settings>
  </labeling>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
</qgis>
