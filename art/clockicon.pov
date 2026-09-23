#version 3.7;
global_settings { assumed_gamma 1.0 }
camera { orthographic location <0, 4, -200> look_at <0, 2, 0> right x*72 up y*72 }
light_source { <-120, 160, -200> srgb <1, 0.95, 0.88>*1.2 area_light <30, 0, 0>, <0, 30, 0>, 3, 3 adaptive 1 }
light_source { <100, -20, -200> srgb 0.35 shadowless }
background { rgbt <0, 0, 0, 1> }
#declare T_Chrome = texture { pigment { srgb <0.90, 0.92, 0.95> } finish { ambient 0 diffuse 0.08 specular 0.9 roughness 0.002 brilliance 3 metallic reflection { 0.75 metallic } } }
#declare T_Brass  = texture { pigment { srgb <0.85, 0.66, 0.28> } finish { ambient 0 diffuse 0.3 specular 0.8 roughness 0.005 metallic reflection { 0.35 metallic } } }
#declare T_Black  = texture { pigment { srgb <0.10, 0.10, 0.12> } finish { ambient 0 diffuse 0.6 specular 0.5 roughness 0.01 } }
union {
  cylinder { <0, 0, -6>, <0, 0, 6>, 26 texture { pigment { srgb <0.78, 0.76, 0.90> } finish { ambient 0 diffuse 0.6 specular 0.7 roughness 0.006 reflection 0.05 } } }
  cylinder { <0, 0, -6.5>, <0, 0, -6.2>, 21 texture { pigment { srgb <0.98, 0.97, 0.94> } finish { ambient 0 diffuse 0.8 } } }
  #for (H, 0, 11) box { <-0.8, 17, -7>, <0.8, 20, -6.5> rotate z*H*30 texture { T_Black } } #end
  box { <-1.4, 0, -7.5>, <1.4, 12, -7> rotate z*-60 texture { T_Black } }
  box { <-1.1, 0, -7.5>, <1.1, 17, -7> rotate z*25 texture { T_Black } }
  sphere { <-19, 22, 0>, 9 scale <1, 0.75, 1> texture { T_Brass } }
  sphere { <19, 22, 0>, 9 scale <1, 0.75, 1> texture { T_Brass } }
  cylinder { <-14, -20, 0>, <-20, -27, 0>, 2 texture { T_Brass } }
  cylinder { <14, -20, 0>, <20, -27, 0>, 2 texture { T_Brass } }
  torus { 21.5, 1.6 rotate x*90 translate <0, 0, -6.5> texture { T_Chrome } }
  translate <0, 2, 0>
}
