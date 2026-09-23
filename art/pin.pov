// DigiCarlo - a map pin, for the program to pin shots to the Photo Board.
// Rendered alone on a clear background (+UA), as seen on the board: from
// the front and a little above. The program draws its shadow on the cork.

#version 3.7;
#ifndef (Colour) #declare Colour = 1; #end    // 1 red, 2 blue, 3 yellow, 4 green, 5 purple

global_settings { assumed_gamma 1.0 }

camera { orthographic location <0, 3, -20> look_at <0, 0, 0> right x*2.6 up y*2.6 }
light_source { <-30, 40, -40> srgb 1.15 area_light <8, 0, 0>, <0, 8, 0>, 5, 5 adaptive 1 circular orient }
light_source { <25, -5, -30> srgb <0.85, 0.9, 1.0>*0.35 shadowless }
background { rgbt <0, 0, 0, 1> }

#declare Colours = array[5] {
  <0.86, 0.16, 0.13>, <0.14, 0.34, 0.86>, <1.00, 0.80, 0.16>, <0.16, 0.62, 0.30>, <0.52, 0.30, 0.80>
}
sphere { 0, 1
  texture { pigment { srgb Colours[Colour - 1] }
            finish { ambient 0 diffuse 0.7 specular 0.9 roughness 0.002 phong 0.4 phong_size 60 } } }
// the collar where the needle goes in, just showing below the head
cone { <0, 0, 0.4>, 0.42, <0, 0, 1.3>, 0.2
       texture { pigment { srgb Colours[Colour - 1] * 0.8 } finish { ambient 0 diffuse 0.6 specular 0.6 roughness 0.01 } } }
