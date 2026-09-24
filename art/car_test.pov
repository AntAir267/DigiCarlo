// Looking at the Metropolitan on its own, from the front left, as a
// photographer would: for checking the model against photographs.
#version 3.7;
#ifndef (Rad) #declare Rad = 0; #end
#ifndef (View) #declare View = 0; #end
global_settings { assumed_gamma 1.0 max_trace_level 10
  #if (Rad) radiosity { pretrace_start 0.08 pretrace_end 0.01 count 100 error_bound 0.8 recursion_limit 1 } #end }
#declare FontCooper = "/home/antair/.local/share/fonts/COOPBL.TTF";
#declare T_Chrome = texture { pigment { srgb <0.90, 0.92, 0.95> }
                              finish { ambient 0 diffuse 0.06 specular 0.9 roughness 0.002 brilliance 3 metallic reflection { 0.78 metallic } } }
#macro Hot(N) #end
#declare HotLights = 0; #declare HotCar = 0;
#include "metropolitan.inc"
#switch (View)
  #case (0) camera { location <-430, 125, -340> look_at <150, 62, 0> angle 38 } #break
  #case (1) camera { location <190, 70, -900> look_at <190, 70, 0> angle 32 } #break
  #case (2) camera { location <-700, 70, 0> look_at <0, 70, 0> angle 20 } #break
#end
light_source { <-600, 900, -700> srgb 1.2 area_light <200, 0, 0>, <0, 0, 200>, 4, 4 adaptive 1 }
light_source { <400, 300, -900> srgb 0.4 shadowless }
sky_sphere { pigment { gradient y color_map { [0 srgb <0.55, 0.6, 0.62>] [1 srgb <0.75, 0.85, 0.95>] } } }
plane { y, 0 texture { pigment { srgb <0.42, 0.5, 0.36> } finish { ambient 0 diffuse 0.8 } } }
object { Metropolitan }
