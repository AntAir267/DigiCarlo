// DigiCarlo - walking up to the Photo Board.
// The board is empty here: the snapshots and session cards are pinned on by
// the program. The ledge carries the dating tools.

#version 3.7;
#ifndef (Rad) #declare Rad = 1; #end

global_settings {
  assumed_gamma 1.0
  max_trace_level 10
  #if (Rad)
  radiosity { pretrace_start 0.08 pretrace_end 0.008 count 160 nearest_count 10 error_bound 0.5
              recursion_limit 2 low_error_factor 0.5 gray_threshold 0 minimum_reuse 0.015 brightness 1 }
  #end
}

#declare FontFranklin = "/home/antair/.local/share/fonts/FRAHV.TTF"
#declare FontNunito   = "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf"

camera { perspective location <0, 14, -760> look_at <0, -2, 0> right x*image_width/image_height angle 49 }

light_source { <-260, 420, -520> srgb <1.0, 0.9, 0.74>*1.15 area_light <80, 0, 0>, <0, 0, 80>, 5, 5 adaptive 1 jitter circular orient }
light_source { <300, 200, -700> srgb <0.85, 0.9, 1.0>*0.3 shadowless }

#declare F_Paint = finish { ambient 0 diffuse 0.62 specular 0.65 roughness 0.006 reflection { 0.03, 0.2 fresnel on } conserve_energy }
#declare T_Red    = texture { pigment { srgb <0.84, 0.19, 0.16> } finish { ambient 0 diffuse 0.7 specular 0.35 roughness 0.01 } }
#declare T_Yellow = texture { pigment { srgb <1.00, 0.84, 0.23> } finish { ambient 0 diffuse 0.75 specular 0.2 roughness 0.02 } }
#declare T_Blue   = texture { pigment { srgb <0.12, 0.31, 0.82> } finish { ambient 0 diffuse 0.7 specular 0.3 roughness 0.01 } }
#declare T_Chrome = texture { pigment { srgb <0.90, 0.92, 0.95> }
                              finish { ambient 0 diffuse 0.06 specular 0.9 roughness 0.002 brilliance 3 metallic reflection { 0.75 metallic } } }
#declare T_Brass  = texture { pigment { srgb <0.85, 0.66, 0.28> } finish { ambient 0 diffuse 0.3 specular 0.8 roughness 0.005 metallic reflection { 0.35 metallic } } }
#declare T_Black  = texture { pigment { srgb <0.10, 0.10, 0.12> } finish { ambient 0 diffuse 0.6 specular 0.5 roughness 0.01 } }

sky_sphere { pigment { gradient y color_map { [0 srgb <0.2, 0.15, 0.1>] [0.55 srgb <0.6, 0.48, 0.36>] [1 srgb <0.9, 0.85, 0.78>] } } }

#macro T_Plank(S, Tone, Rot)
  texture {
    pigment { wood turbulence 0.07 octaves 3 omega 0.45
      color_map { [0.00 srgb Tone*1.00] [0.30 srgb Tone*0.94] [0.55 srgb Tone*0.80] [0.80 srgb Tone*0.96] [1.00 srgb Tone*1.00] }
      scale <2.2, 2.2, 1> rotate Rot translate <rand(S)*60, rand(S)*300, rand(S)*60> }
    normal { wood 0.2 turbulence 0.07 scale <2.2, 2.2, 1> rotate Rot }
    finish { ambient 0 diffuse 0.72 specular 0.06 roughness 0.05 }
  }
#end
#macro Img(File, W, H)
  pigment { image_map { png File interpolate 2 } scale <W, H, 1> }
  finish { ambient 0 diffuse 0.8 specular 0.05 }
#end
#declare S = seed(5);

// the wall behind
union {
  #for (I, 0, 60)
    #local X0 = -480 + I*16;
    box { <X0 + 0.35, -200, 20>, <X0 + 15.65, 300, 24> T_Plank(S, <0.80, 0.53, 0.31>*(0.9 + 0.14*rand(S)), x*90) }
  #end
  box { <-500, -200, 24>, <500, 300, 30> pigment { srgb <0.2, 0.11, 0.05> } }
}

// the board
#declare BX = 318; #declare BT = 132; #declare BB = -86;
union {
  box { <-BX - 12, BT, 4>, <BX + 12, BT + 12, 20> }
  box { <-BX - 12, BB - 12, 4>, <BX + 12, BB, 20> }
  box { <-BX - 12, BB - 12, 4>, <-BX, BT + 12, 20> }
  box { <BX, BB - 12, 4>, <BX + 12, BT + 12, 20> }
  texture { T_Red }
}
box {
  <-BX, BB, 12>, <BX, BT, 20>
  texture {
    pigment { granite scale 5 color_map { [0 srgb <0.68, 0.48, 0.28>] [0.5 srgb <0.78, 0.58, 0.35>] [1 srgb <0.60, 0.41, 0.23>] } }
    normal { granite 0.6 scale 0.9 }
    finish { ambient 0 diffuse 0.8 specular 0.02 }
  }
}
// banner
box { <-110, BT - 32, 9>, <110, BT - 6, 11.5> texture { T_Yellow } }
#declare Ban = text { ttf FontFranklin "Photo Board" 0.06, 0 }
#declare Mn = min_extent(Ban); #declare Mx = max_extent(Ban);
object { Ban translate -<(Mn.x + Mx.x)/2, (Mn.y + Mx.y)/2, 0>
         matrix <1, 0, 0, 0.22, 1, 0, 0, 0, 1, 0, 0, 0>
         scale 22 translate <0, BT - 19, 8.6> texture { T_Blue } }

// the ledge
box { <-BX - 40, BB - 26, -64>, <BX + 40, BB - 12, 12> T_Plank(S, <0.86, 0.60, 0.36>, y*90) }
box { <-BX - 40, BB - 46, -66>, <BX + 40, BB - 26, -58> T_Plank(S, <0.72, 0.47, 0.27>, y*90) }
#declare LY = BB - 12;     // ledge top

// a date stamp
union {
  box { <-22, 0, -12>, <22, 10, 12> texture { T_Black } }
  box { <-18, 10, -8>, <18, 34, 8> texture { T_Black } }
  box { <-15, 14, -8.4>, <15, 26, -8> texture { pigment { srgb <0.14, 0.14, 0.16> } } }
  #declare Dt = text { ttf FontNunito "SEP 20" 0.05, 0 }
  object { Dt translate -<(min_extent(Dt).x + max_extent(Dt).x)/2, 0, 0> scale 8 translate <0, 17, -8.6> texture { pigment { srgb <1, 0.84, 0.23> } finish { ambient 0 emission 0.2 } } }
  cylinder { <0, 34, 0>, <0, 44, 0>, 5 T_Plank(S, <0.55, 0.33, 0.17>, x*90) }
  sphere { <0, 52, 0>, 12 scale <1, 0.8, 1> T_Plank(S, <0.60, 0.35, 0.18>, x*90) }
  translate <-190, LY, -30>
}
box { <0, 0, -0.2>, <46, 12, 0.2> texture { Img("tex/t_stamp.png", 46, 12) } rotate z*-2 translate <-213, BB - 40, -67> }

// an alarm clock: the camera's own clock
union {
  cylinder { <0, 0, -6>, <0, 0, 6>, 26 texture { pigment { srgb <0.78, 0.76, 0.90> } finish { ambient 0 diffuse 0.6 specular 0.7 roughness 0.006 reflection 0.05 } } }
  cylinder { <0, 0, -6.5>, <0, 0, -6.2>, 21 texture { pigment { srgb <0.98, 0.97, 0.94> } finish { ambient 0 diffuse 0.8 } } }
  #for (H, 0, 11)
    box { <-0.8, 17, -7>, <0.8, 20, -6.5> rotate z*H*30 texture { T_Black } }
  #end
  box { <-1.2, 0, -7.5>, <1.2, 12, -7> rotate z*-60 texture { T_Black } }
  box { <-1, 0, -7.5>, <1, 17, -7> rotate z*25 texture { T_Black } }
  sphere { <-19, 22, 0>, 9 scale <1, 0.75, 1> texture { T_Brass } }
  sphere { <19, 22, 0>, 9 scale <1, 0.75, 1> texture { T_Brass } }
  cylinder { <-14, -20, 0>, <-20, -27, 0>, 2 texture { T_Brass } }
  cylinder { <14, -20, 0>, <20, -27, 0>, 2 texture { T_Brass } }
  torus { 21.5, 1.6 rotate x*90 translate <0, 0, -6.5> texture { T_Chrome } }
  translate <-60, LY + 27, -30>
}
box { <0, 0, -0.2>, <50, 12, 0.2> texture { Img("tex/t_clock.png", 50, 12) } rotate z*1.5 translate <-85, BB - 40, -67> }

// an eraser: back to automatic
union {
  superellipsoid { <0.2, 0.2> scale <18, 8, 9> translate <-10, 0, 0> texture { pigment { srgb <1.0, 0.63, 0.70> } finish { ambient 0 diffuse 0.8 specular 0.2 roughness 0.05 } } }
  superellipsoid { <0.2, 0.2> scale <12, 8, 9> translate <18, 0, 0> texture { pigment { srgb <0.45, 0.68, 0.92> } finish { ambient 0 diffuse 0.8 specular 0.2 roughness 0.05 } } }
  rotate z*8 rotate y*-15 translate <62, LY + 9, -32>
}
box { <0, 0, -0.2>, <44, 12, 0.2> texture { Img("tex/t_eraser.png", 44, 12) } rotate z*-1 translate <42, BB - 40, -67> }

// a wastebasket: leave out
difference {
  cone { <0, 0, 0>, 17, <0, 46, 0>, 22 }
  cone { <0, 2, 0>, 15.5, <0, 47, 0>, 20.5 }
  #for (A, 0, 350, 20)
    box { <-1.2, 8, -30>, <1.2, 38, 0> rotate y*A }
  #end
  texture { pigment { srgb <0.62, 0.66, 0.70> } finish { ambient 0 diffuse 0.4 specular 0.8 roughness 0.006 metallic reflection 0.25 } }
  translate <185, LY, -30>
}
torus { 22, 1.6 translate <185, LY + 46, -30> texture { T_Chrome } }
box { <0, 0, -0.2>, <44, 12, 0.2> texture { Img("tex/t_bin.png", 44, 12) } rotate z*2 translate <163, BB - 40, -67> }
