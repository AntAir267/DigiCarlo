// DigiCarlo - the garage, pre-rendered the 1995 way.
// Units are centimetres. x right, y up, z into the scene; the back wall is
// at z = 400.

#version 3.7;

// What render.sh switches, to cut the pieces the program swaps in:
#ifndef (Rad) #declare Rad = 1; #end          // bounced light
#ifndef (Area) #declare Area = 1; #end        // soft shadows
#ifndef (Reuse) #declare Reuse = 0; #end      // bounced light from a saved file
#ifndef (Card) #declare Card = 1; #end        // a card in the reader
#ifndef (Blink) #declare Blink = 1; #end      // the SiPix on the bench
#ifndef (Safe) #declare Safe = 1; #end        // the darkroom's safelight on
#ifndef (Lamp) #declare Lamp = 1; #end        // the light over the car on (0: the garage in the dark)
#ifndef (Beams) #declare Beams = 0; #end      // the car's headlights on
#ifndef (Hide) #declare Hide = 0; #end        // leave out one clickable thing, to find its outline

// Clickable things, numbered for Hide; the program's hotspots follow these.
#declare HotCard = 1; #declare HotBlink = 2; #declare HotDoor = 3;
#declare HotBoard = 4; #declare HotCrate = 5; #declare HotCar = 6;
#declare HotLamp = 7; #declare HotLights = 8;
#macro Hot(N) #if (Hide = N) no_image #end #end

global_settings {
  assumed_gamma 1.0
  max_trace_level 10
  #if (Rad)
  radiosity {
    // Reused, the bounced light is the same in every render, so the pieces
    // cut from one fit the others without a seam.
    #if (Reuse) pretrace_start 1 pretrace_end 1 always_sample off
    #else pretrace_start 0.08 pretrace_end 0.008 #end
    count 180 nearest_count 10 error_bound 0.5
    recursion_limit 2 low_error_factor 0.5
    gray_threshold 0.0 minimum_reuse 0.015
    brightness 1.0 adc_bailout 0.005
  }
  #end
}

#declare FontCooper   = "/home/antair/.local/share/fonts/COOPBL.TTF"
#declare FontFranklin = "/home/antair/.local/share/fonts/FRAHV.TTF"
#declare FontNunito   = "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf"

camera {
  perspective
  location <-10, 138, -150>
  look_at  <0, 118, 400>
  right x*image_width/image_height
  angle 72
}

// ---------------------------------------------------------------------------
// Materials
// ---------------------------------------------------------------------------

#declare F_Paint = finish { ambient 0 diffuse 0.62 specular 0.65 roughness 0.006
                            reflection { 0.03, 0.2 fresnel on } conserve_energy }
#declare T_Carib  = texture { pigment { srgb <0.18, 0.64, 0.73> } finish { F_Paint } }
#declare T_Snow   = texture { pigment { srgb <0.95, 0.93, 0.86> } finish { F_Paint } }
#declare T_Red    = texture { pigment { srgb <0.84, 0.19, 0.16> } finish { ambient 0 diffuse 0.7 specular 0.35 roughness 0.01 } }
#declare T_Yellow = texture { pigment { srgb <1.00, 0.84, 0.23> } finish { ambient 0 diffuse 0.75 specular 0.2 roughness 0.02 } }
#declare T_Blue   = texture { pigment { srgb <0.12, 0.31, 0.82> } finish { ambient 0 diffuse 0.7 specular 0.3 roughness 0.01 } }
#declare T_White  = texture { pigment { srgb <0.97, 0.96, 0.92> } finish { ambient 0 diffuse 0.8 specular 0.1 } }
#declare T_Chrome = texture { pigment { srgb <0.90, 0.92, 0.95> }
                              finish { ambient 0 diffuse 0.06 specular 0.9 roughness 0.002
                                       brilliance 3 metallic reflection { 0.78 metallic } } }
#declare T_Brass  = texture { pigment { srgb <0.85, 0.66, 0.28> }
                              finish { ambient 0 diffuse 0.3 specular 0.8 roughness 0.005 metallic reflection { 0.35 metallic } } }
#declare T_Rubber = texture { pigment { srgb <0.07, 0.07, 0.08> } finish { ambient 0 diffuse 0.6 specular 0.12 roughness 0.05 } }
#declare T_DarkPlastic = texture { pigment { srgb <0.22, 0.25, 0.28> } finish { ambient 0 diffuse 0.6 specular 0.5 roughness 0.01 } }
#declare T_DoorPaint = texture { pigment { srgb <0.17, 0.16, 0.21> } finish { ambient 0 diffuse 0.6 specular 0.3 roughness 0.02 } }

#macro T_Plank(S, Tone, Rot)
  texture {
    pigment {
      wood turbulence 0.07 octaves 3 omega 0.45
      color_map {
        [0.00 srgb Tone*1.00] [0.30 srgb Tone*0.94] [0.55 srgb Tone*0.80]
        [0.80 srgb Tone*0.96] [1.00 srgb Tone*1.00]
      }
      scale <2.2, 2.2, 1> rotate Rot
      translate <rand(S)*60, rand(S)*300, rand(S)*60>
    }
    normal { wood 0.2 turbulence 0.07 scale <2.2, 2.2, 1> rotate Rot }
    finish { ambient 0 diffuse 0.72 specular 0.06 roughness 0.05 }
  }
#end

#macro Img(File, W, H)
  pigment { image_map { png File interpolate 2 } scale <W, H, 1> }
  finish { ambient 0 diffuse 0.8 specular 0.05 }
#end

#declare S = seed(21);

// ---------------------------------------------------------------------------
// Lights: the pendant lamp, daylight through the window, the safelight
// ---------------------------------------------------------------------------

#if (Lamp)
light_source {
  <25, 212, 250> srgb <1.0, 0.86, 0.66>*1.25
  #if (Area) area_light <26, 0, 0>, <0, 0, 26>, 7, 7 adaptive 1 circular orient #end
  fade_distance 200 fade_power 1.4
}
light_source { <220, 230, 120> srgb <1.0, 0.9, 0.75>*0.55 fade_distance 220 fade_power 1.2 }
#end
// fill from the open side of the room; dimmer with the light off
light_source { <-30, 170, -140> srgb <0.9, 0.93, 1.0>*(Lamp ? 0.42 : 0.12) shadowless }
light_source {
  <-900, 900, 1500> srgb <1.0, 0.95, 0.85>*1.6 parallel point_at <-190, 0, 330>
}
#if (Safe) light_source { <-27, 212, 388> srgb <1.0, 0.16, 0.08>*1.2 fade_distance 38 fade_power 2 } #end

// The sky Windows 95 started with: blue, and fat white clouds.
sky_sphere {
  pigment { gradient y color_map { [0.0 srgb <0.62, 0.80, 0.97>] [0.35 srgb <0.30, 0.55, 0.92>] [1.0 srgb <0.16, 0.38, 0.84>] } }
  pigment {
    bozo turbulence 0.55 octaves 6 omega 0.55 lambda 2.2
    color_map { [0.00 rgbt <1, 1, 1, 1>] [0.52 rgbt <1, 1, 1, 1>] [0.66 rgbt <1, 1, 1, 0.3>] [1.00 rgbt <1, 1, 1, 0>] }
    scale <0.22, 0.07, 0.22> translate <0.3, 0.05, 0>
  }
}

// outside: lawn, a hedge and a tree, lit by the sun alone (so the car's
// headlights, shining at the window, do not light the hills)
light_group {
  plane { y, -0.5 texture { pigment { srgb <0.36, 0.66, 0.26> } finish { ambient 0 diffuse 0.8 } } }
  union {
    #for (I, 0, 30)
      sphere { <-900 + I*55, 45 + rand(S)*20, 1100 + rand(S)*60>, 70 + rand(S)*20 }
    #end
    texture { pigment { granite scale 30 color_map { [0 srgb <0.20, 0.45, 0.18>] [1 srgb <0.30, 0.58, 0.24>] } } finish { ambient 0 diffuse 0.8 } }
  }
  union {
    cylinder { <-80, 0, 800>, <-80, 260, 800>, 16 texture { pigment { srgb <0.40, 0.25, 0.14> } } }
    #for (I, 0, 9)
      sphere { <-80 + (rand(S)-0.5)*220, 300 + rand(S)*140, 800 + (rand(S)-0.5)*80>, 80 + rand(S)*40
               texture { pigment { granite scale 40 color_map { [0 srgb <0.18, 0.45, 0.16>] [1 srgb <0.32, 0.62, 0.22>] } } finish { ambient 0 diffuse 0.8 } } }
    #end
  }

  light_source { <-900, 900, 1500> srgb <1.0, 0.95, 0.85>*1.6 parallel point_at <-190, 0, 330> }
  global_lights off
}

// ---------------------------------------------------------------------------
// The room
// ---------------------------------------------------------------------------

#declare WindowHole = box { <-285, 112, 380>, <-118, 232, 430> }
#declare DoorHole   = box { <-70, -1, 380>, <16, 206, 430> }

difference {
  union {
    #for (I, 0, 50)
      #local X0 = -330 + I*16;
      box { <X0 + 0.35, 0, 400>, <X0 + 15.65, 262, 404>
            T_Plank(S, <0.80, 0.53, 0.31>*(0.90 + 0.14*rand(S)), x*90) }
    #end
    box { <-340, 0, 404.2>, <480, 270, 410> pigment { srgb <0.20, 0.11, 0.05> } }
  }
  object { WindowHole }
  object { DoorHole }
}

// left wall, boards laid horizontally
union {
  #for (I, 0, 16)
    box { <-342, I*16 + 0.35, -300>, <-338, I*16 + 15.65, 404>
          T_Plank(S, <0.72, 0.47, 0.27>*(0.9 + 0.14*rand(S)), y*90) }
  #end
  box { <-346, 0, -300>, <-342, 270, 404> pigment { srgb <0.20, 0.11, 0.05> } }
}

// ceiling and beams
box { <-350, 262, -300>, <500, 280, 410> T_Plank(S, <0.45, 0.28, 0.15>, y*90) }
#for (Z, 60, 330, 135)
  box { <-350, 246, Z>, <500, 262, Z + 16> T_Plank(S, <0.55, 0.33, 0.17>, y*90) }
#end
// baseboard
box { <-340, 0, 394>, <480, 11, 400> T_Plank(S, <0.45, 0.27, 0.14>, y*90) }
// the wall behind the camera: never seen, but the chrome reflects it
union {
  #for (I, 0, 52)
    #local X0 = -350 + I*16;
    box { <X0 + 0.35, 0, -266>, <X0 + 15.65, 262, -262>
          T_Plank(S, <0.80, 0.53, 0.31>*(0.90 + 0.14*rand(S)), x*90) }
  #end
  box { <-350, 0, -272>, <500, 270, -266> pigment { srgb <0.20, 0.11, 0.05> } }
}

// concrete floor, with a joint and an oil stain
box {
  <-350, -2, -300>, <500, 0, 404>
  texture {
    pigment { granite turbulence 0.3 color_map { [0 srgb <0.58, 0.56, 0.52>] [0.5 srgb <0.66, 0.64, 0.60>] [1 srgb <0.72, 0.70, 0.66>] } scale 50 }
    normal { granite 0.1 scale 3 }
    finish { ambient 0 diffuse 0.78 specular 0.15 roughness 0.03 reflection 0.025 }
  }
}
box { <-350, 0, 250>, <500, 0.12, 251.2> pigment { srgb <0.42, 0.41, 0.39> } }
box { <90, 0, -300>, <91.2, 0.12, 404> pigment { srgb <0.42, 0.41, 0.39> } }

// ---------------------------------------------------------------------------
// The window
// ---------------------------------------------------------------------------

union {
  box { <-292, 104, 394>, <-111, 112, 401> }
  box { <-292, 232, 394>, <-111, 240, 401> }
  box { <-292, 104, 394>, <-285, 240, 401> }
  box { <-118, 104, 394>, <-111, 240, 401> }
  box { <-205, 112, 397>, <-199, 232, 400> }
  box { <-285, 169, 397>, <-118, 175, 400> }
  box { <-298, 98, 386>, <-105, 104, 401> }         // sill
  T_Plank(S, <0.88, 0.66, 0.43>, y*90)
}
light_group {
  box { <-285, 112, 398.5>, <-118, 232, 399> texture { pigment { srgbf <0.9, 0.95, 1.0, 0.92> } finish { ambient 0 diffuse 0 specular 0.8 roughness 0.001 reflection 0.025 } } }
  light_source { <-900, 900, 1500> srgb <1.0, 0.95, 0.85>*1.6 parallel point_at <-190, 0, 330> }
  global_lights off
}

// ---------------------------------------------------------------------------
// The Pick-Up Bench
// ---------------------------------------------------------------------------

union {
  box { <-302, 84, 318>, <-96, 92, 399> }                     // top
  box { <-298, 66, 316>, <-100, 84, 322> }                    // apron
  box { <-298, 0, 318>, <-289, 84, 327> }
  box { <-109, 0, 318>, <-100, 84, 327> }
  box { <-298, 0, 389>, <-289, 84, 398> }
  box { <-109, 0, 389>, <-100, 84, 398> }
  box { <-298, 17, 322>, <-100, 22, 396> }                    // lower shelf
  T_Plank(S, <0.86, 0.60, 0.36>, y*90)
}
// its painted sign
box { <-262, 68, 314.6>, <-136, 82.5, 316.2> texture { T_Snow } }
text { ttf FontCooper "Pick-Up Bench" 0.05, 0 scale 12.5 translate <-257.5, 71, 314.4> texture { T_Red } }

// a card reader; its light is on when a card is in it
superellipsoid { <0.25, 0.25> scale <17, 5, 10> translate <-244, 97, 352> texture { T_DarkPlastic } }
sphere { <-231, 100, 342.3>, 1.3
         texture { #if (Card) pigment { srgb <0.3, 1, 0.3> } finish { ambient 0 emission 1 }
                   #else pigment { srgb <0.10, 0.22, 0.12> } finish { ambient 0 diffuse 0.5 specular 0.8 roughness 0.005 } #end } }
// the card, with a luggage tag on a string. The program writes the card's
// name on its label and how many pictures are new on the tag.
#if (Card)
union {
  box {
    <0, 0, -0.9>, <13, 18, 0.9>
    texture { Img("tex/sdcard.png", 13, 18) }
    rotate x*-8 translate <-252, 99, 352>
  }
  cylinder { <-233, 101, 350>, <-214, 96, 344>, 0.25 texture { pigment { srgb 0.25 } } }
  box { <0, 0, -0.2>, <26, 11.5, 0.2> texture { Img("tex/tag.png", 26, 11.5) } rotate z*8 rotate y*-12 translate <-214, 88, 343> }
  Hot(HotCard)
}
#end

// the SiPix Blink II, on its cable
#if (Blink)
union {
  union {
    superellipsoid { <0.4, 0.4> scale <14, 9, 7> texture { pigment { srgb <0.78, 0.76, 0.90> } finish { ambient 0 diffuse 0.6 specular 0.6 roughness 0.008 } } }
    cylinder { <-3, 1, -6.5>, <-3, 1, -8.5>, 5.2 texture { T_Chrome } }
    cylinder { <-3, 1, -8.4>, <-3, 1, -8.7>, 3.6 texture { pigment { srgb <0.06, 0.07, 0.10> } finish { ambient 0 specular 0.9 roughness 0.001 reflection 0.3 } } }
    sphere { <8, 8.5, -2>, 2 texture { T_Red } }
    translate <-160, 101, 352>
  }
  cylinder { <-146, 100, 352>, <-122, 92, 330>, 0.6 texture { T_Rubber } }
  cylinder { <-122, 92, 330>, <-110, 60, 316>, 0.6 texture { T_Rubber } }
  Hot(HotBlink)
}
#end

// a desk lamp at the end of the bench
union {
  cylinder { <0, 0, 0>, <0, 2.5, 0>, 9 }
  cylinder { <0, 2, 0>, <-10, 40, 4>, 1.3 }
  cylinder { <-10, 40, 4>, <-28, 52, -2>, 1.3 }
  cone { <-28, 52, -2>, 3, <-36, 42, -6>, 11 open }
  texture { pigment { srgb <0.17, 0.43, 0.62> } finish { ambient 0 diffuse 0.6 specular 0.6 roughness 0.008 } }
  translate <-118, 92, 380>
}
sphere { <-152, 136, 375>, 3.5 texture { pigment { srgb <1, 0.95, 0.75> } finish { ambient 0 emission 1 } } no_shadow }
light_source { <-152, 132, 373> srgb <1, 0.9, 0.7>*0.5 fade_distance 40 fade_power 2 }

// the crate of originals
union {
  difference {
    box { <0, 0, 0>, <62, 34, 40> }
    box { <3, 4, 3>, <59, 40, 37> }
    #for (I, 0, 5)
      box { <5 + I*9.5, 8, -1>, <11 + I*9.5, 16, 41> }
      box { <5 + I*9.5, 20, -1>, <11 + I*9.5, 28, 41> }
    #end
    texture { pigment { srgb <0.17, 0.46, 0.86> } finish { ambient 0 diffuse 0.65 specular 0.5 roughness 0.01 } }
  }
  box { <0, 0, -0.4>, <42, 8, 0> texture { Img("tex/originals.png", 42, 8) } translate <10, 22, -0.1> }
  #declare Albums = array[4] { <0.19, 0.66, 0.31>, <0.85, 0.20, 0.16>, <1.0, 0.84, 0.23>, <0.49, 0.36, 0.79> }
  #for (I, 0, 3)
    box { <6 + I*13, 4, 8>, <17 + I*13, 46 - I*2, 32>
          texture { pigment { srgb Albums[I] } finish { ambient 0 diffuse 0.7 specular 0.3 } } }
  #end
  translate <-262, 0, 290>
  Hot(HotCrate)
}

// ---------------------------------------------------------------------------
// The darkroom
// ---------------------------------------------------------------------------

union {
  union {
    box { <-77, 0, 396>, <-70, 214, 401> }
    box { <16, 0, 396>, <23, 214, 401> }
    box { <-77, 206, 396>, <23, 214, 401> }
    T_Plank(S, <0.88, 0.66, 0.43>, y*90)
  }
  box { <-69, 0, 402>, <15, 205, 405> texture { T_DoorPaint } }
  box { <-60, 18, 401.2>, <6, 88, 402.2> texture { T_DoorPaint } }
  box { <-60, 104, 401.2>, <6, 132, 402.2> texture { T_DoorPaint } }
  box { <-58, 150, 400.6>, <4, 166, 402> texture { T_Red } }
  text { ttf FontCooper "DARKROOM" 0.05, 0 scale 8.4 translate <-54.5, 154.5, 400.4> texture { T_White } }
  box { <0, 0, -0.2>, <42, 16, 0.2> texture { Img("tex/develop.png", 42, 16) } rotate z*3 translate <-48, 133, 400.8> }
  sphere { <7, 98, 400.2>, 3.2 texture { T_Brass } }
  Hot(HotDoor)
}
// the safelight: on while there are shots waiting to be developed
box { <-36, 226, 391>, <-18, 231, 400> texture { T_DarkPlastic } }
#if (Safe)
sphere { <-27, 219, 392>, 7 texture { pigment { srgb <1, 0.2, 0.1> } finish { ambient 0 emission 0.95 diffuse 0.2 } } no_shadow }
#else
sphere { <-27, 219, 392>, 7 texture { pigment { srgbf <0.55, 0.12, 0.08, 0.3> } finish { ambient 0 emission 0.04 diffuse 0.4 specular 0.8 roughness 0.004 reflection 0.1 } } }
#end
torus { 7.2, 0.5 rotate x*90 translate <-27, 219, 392> texture { T_DarkPlastic } }
torus { 7.2, 0.5 translate <-27, 219, 392> texture { T_DarkPlastic } }

// ---------------------------------------------------------------------------
// The Photo Board
// ---------------------------------------------------------------------------

#declare BX0 = 44; #declare BX1 = 220; #declare BY0 = 106; #declare BY1 = 230;
union {
union {
  box { <BX0, BY0, 392>, <BX1, BY0 + 8, 400> }
  box { <BX0, BY1 - 8, 392>, <BX1, BY1, 400> }
  box { <BX0, BY0, 392>, <BX0 + 8, BY1, 400> }
  box { <BX1 - 8, BY0, 392>, <BX1, BY1, 400> }
  texture { T_Red }
}
box {
  <BX0 + 8, BY0 + 8, 396>, <BX1 - 8, BY1 - 8, 399>
  texture {
    pigment { granite scale 4 color_map { [0 srgb <0.68, 0.48, 0.28>] [0.5 srgb <0.78, 0.58, 0.35>] [1 srgb <0.60, 0.41, 0.23>] } }
    normal { granite 0.6 scale 0.7 }
    finish { ambient 0 diffuse 0.8 specular 0.02 }
  }
}
// banner
box { <BX0 + 16, BY1 - 34, 394.6>, <BX1 - 16, BY1 - 15, 395.9> texture { T_Yellow } }
text {
  ttf FontFranklin "Photo Board" 0.06, 0
  matrix <1, 0, 0, 0.22, 1, 0, 0, 0, 1, 0, 0, 0>
  scale 15 translate <BX0 + 29, BY1 - 30.5, 394.4> texture { T_Blue }
}
// snapshots, pinned
#declare Snap = array[7][4] {
  {BX0 + 14, BY0 + 50, -6, 0}, {BX0 + 44, BY0 + 52, 4, 1}, {BX0 + 74, BY0 + 49, -3, 2},
  {BX0 + 16, BY0 + 14, 5, 3}, {BX0 + 46, BY0 + 13, -4, 4}, {BX0 + 104, BY0 + 51, 6, 6},
  {BX0 + 106, BY0 + 15, -2, 7}
}
#declare Pins = array[4] { <0.85, 0.2, 0.16>, <0.12, 0.31, 0.82>, <0.18, 0.66, 0.31>, <1.0, 0.84, 0.23> }
#for (I, 0, 6)
  box {
    <0, 0, -0.25>, <24, 29, 0.25>
    texture { Img(concat("tex/snap", str(Snap[I][3], 0, 0), ".png"), 24, 29) }
    rotate z*Snap[I][2] translate <Snap[I][0], Snap[I][1], 395.2>
  }
  sphere { <Snap[I][0] + 12, Snap[I][1] + 27, 393.8>, 1.6
           texture { pigment { srgb Pins[mod(I, 4)] } finish { ambient 0 diffuse 0.6 specular 0.9 roughness 0.002 reflection 0.1 } } }
#end
// a sticky note: the program writes on it how many shots are waiting
box { <0, 0, -0.2>, <27, 27, 0.2> texture { Img("tex/sticky.png", 27, 27) } rotate z*-5 translate <BX0 + 136, BY0 + 16, 395.3> }
sphere { <BX0 + 150, BY0 + 42, 393.8>, 1.6 texture { T_Red } }
Hot(HotBoard)
}

// ---------------------------------------------------------------------------
// The calendar: the program prints today on it, which is the date a pull's
// newest shot gets
// ---------------------------------------------------------------------------

box { <0, 0, -0.3>, <42, 59, 0.3> texture { Img("tex/calendar.png", 42, 59) } translate <232, 150, 399.2> }
sphere { <253, 211, 399>, 1.2 texture { T_Chrome } }

// ---------------------------------------------------------------------------
// The Metropolitan, nosing in
// ---------------------------------------------------------------------------

#include "metropolitan.inc"
object { Metropolitan scale 0.95 rotate y*-28 translate <150, 0, 240> Hot(HotCar) }

// the pendant lamp, which can be switched off
union {
  cylinder { <25, 262, 250>, <25, 228, 250>, 0.5 texture { pigment { srgb 0.1 } } }
  cone { <25, 228, 250>, 3, <25, 214, 250>, 16 open texture { pigment { srgb <0.85, 0.20, 0.16> } finish { ambient 0 diffuse 0.7 specular 0.5 roughness 0.01 } } }
  sphere { <25, 215, 250>, 4.5
           texture { #if (Lamp) pigment { srgb <1, 0.95, 0.8> } finish { ambient 0 emission 1 }
                     #else pigment { srgbf <0.9, 0.9, 0.85, 0.4> } finish { ambient 0 emission 0.03 diffuse 0.3 specular 0.9 roughness 0.002 reflection 0.1 } #end }
           no_shadow }
  Hot(HotLamp)
}
