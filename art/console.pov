// DigiCarlo - the console along the bottom of the window.
// Fallout's interface bar, built as 1956 Nash Metropolitan hardware, with
// Techno Drive's cluster of buttons in the middle. Units are pixels of the
// final image; the camera looks straight at the panel.

#version 3.7;
// What render.sh switches, to cut the pieces the program swaps in:
#ifndef (Rad) #declare Rad = 1; #end        // bounced light
#ifndef (Reuse) #declare Reuse = 0; #end    // bounced light from a saved file
#ifndef (Mode) #declare Mode = 0; #end      // 0 the garage, 1 the photo board
#ifndef (Lit) #declare Lit = 0; #end        // the radio key pushed in (0 = none)
#ifndef (Go) #declare Go = 0; #end          // START: 0 resting, 1 lit, 2 lit as STOP
#ifndef (Digit) #declare Digit = 0; #end    // what every counter drum shows
#ifndef (Hide) #declare Hide = 0; #end      // leave out one clickable thing, to find its outline

// Clickable things, numbered for Hide: keys 1-5, then these.
#declare HotKnobL = 6; #declare HotKnobR = 7; #declare HotStart = 8;
#declare HotScreen = 9; #declare HotCounter = 10;
#macro Hot(N) #if (Hide = N) no_image #end #end

global_settings {
  assumed_gamma 1.0
  max_trace_level 10
  #if (Rad)
  radiosity {
    #if (Reuse) pretrace_start 1 pretrace_end 1 always_sample off
    #else pretrace_start 0.08 pretrace_end 0.01 #end
    count 120 nearest_count 8 error_bound 0.7
    recursion_limit 1 low_error_factor 0.5 gray_threshold 0 brightness 1 }
  #end
}

#declare FontNunito = "/usr/share/fonts/truetype/nunito/Nunito-Black.ttf"
#declare FontCooper = "/home/antair/.local/share/fonts/COOPBL.TTF"
#declare FontScript = "/home/antair/.local/share/fonts/SCRIPTBL.TTF"
#declare FontDigits = "/home/antair/.local/share/fonts/COOPBL.TTF"

camera { orthographic location <0, 150, -800> look_at <0, 0, 0> right x*1272 up y*230 }

light_source { <-500, 700, -900> srgb <1, 0.96, 0.9>*1.1 area_light <200, 0, 0>, <0, 200, 0>, 6, 6 adaptive 1 }
light_source { <700, -200, -700> srgb <0.8, 0.88, 1.0>*0.35 shadowless }
light_source { <0, 300, -300> srgb 0.25 shadowless }

#declare F_Paint = finish { ambient 0 diffuse 0.6 specular 0.7 roughness 0.005 reflection { 0.04, 0.2 fresnel on } conserve_energy }
#declare T_Carib = texture { pigment { srgb <0.18, 0.64, 0.73> } finish { F_Paint } }
#declare T_CaribDeep = texture { pigment { srgb <0.10, 0.42, 0.50> } finish { F_Paint } }
#declare T_Snow = texture { pigment { srgb <0.95, 0.93, 0.86> } finish { F_Paint } }
#declare T_Bakelite = texture { pigment { srgb <0.96, 0.92, 0.80> } finish { ambient 0 diffuse 0.6 specular 0.8 roughness 0.004 reflection 0.06 } }
#declare T_Chrome = texture { pigment { srgb <0.90, 0.92, 0.95> }
                              finish { ambient 0 diffuse 0.08 specular 0.9 roughness 0.002 brilliance 3 metallic reflection { 0.75 metallic } } }
#declare T_Ink = texture { pigment { srgb <0.11, 0.16, 0.19> } finish { ambient 0 diffuse 0.7 specular 0.2 } }
#declare T_Red = texture { pigment { srgb <0.84, 0.16, 0.13> } finish { ambient 0 diffuse 0.6 specular 0.8 roughness 0.004 reflection 0.08 } }
#declare T_Lamp = texture { pigment { srgb <1.0, 0.78, 0.2> } finish { ambient 0 emission 1.0 diffuse 0.3 } }

// the reflections chrome picks up: a warm garage above, dark below
sky_sphere { pigment { gradient y color_map { [0 srgb <0.08, 0.07, 0.07>] [0.5 srgb <0.45, 0.36, 0.28>] [0.6 srgb <0.95, 0.88, 0.75>] [1 srgb <0.55, 0.62, 0.72>] } } }

#macro Screw(P)
  union {
    sphere { 0, 5 scale <1, 1, 0.45> texture { T_Chrome } }
    box { <-4, -0.8, -3>, <4, 0.8, 0> texture { pigment { srgb 0.2 } } rotate z*35 }
    translate P
  }
#end

#macro Label(Text, Font, Size, Pos, Tex)
  #local T = text { ttf Font Text 0.05, 0 }
  #local Mn = min_extent(T); #local Mx = max_extent(T);
  object { T translate -<(Mn.x + Mx.x)/2, (Mn.y + Mx.y)/2, 0> scale Size translate Pos texture { Tex } }
#end

// ---------------------------------------------------------------------------
// the panel itself: enamel, chrome rods top and bottom
// ---------------------------------------------------------------------------

superellipsoid { <0.12, 0.35> scale <700, 114, 40> translate <0, 0, 40> texture { T_Carib } }
cylinder { <-700, 109, -2>, <700, 109, -2>, 5 texture { T_Chrome } }
cylinder { <-700, -109, -2>, <700, -109, -2>, 5 texture { T_Chrome } }

// ---------------------------------------------------------------------------
// the message screen, in a Snowberry bezel
// ---------------------------------------------------------------------------

#declare SX = -412;
difference {
  superellipsoid { <0.22, 0.22> scale <206, 92, 16> translate <SX, 0, -2> }
  superellipsoid { <0.22, 0.22> scale <178, 72, 30> translate <SX, 2, -10> }
  texture { T_Snow }
}
box { <SX - 190, -82, 2>, <SX + 190, 86, 22> pigment { srgb 0.01 } }
box { <SX - 179, -71, -1>, <SX + 179, 75, 0>
  texture { pigment { srgb <0.05, 0.16, 0.09> } finish { ambient 0 emission 0.16 diffuse 0.2 specular 0.6 roughness 0.01 reflection 0.03 } }
  Hot(HotScreen) }
Screw(<SX - 194, 80, -18>) Screw(<SX + 194, 80, -18>) Screw(<SX - 194, -80, -18>) Screw(<SX + 194, -80, -18>)

// ---------------------------------------------------------------------------
// the radio: a 1950s push-button set. The stations on its dial are what the
// keys do; the chosen key stays pushed in and the needle swings to it.
// ---------------------------------------------------------------------------

#declare Digits = array[4] { str(Digit, 0, 0), str(Digit, 0, 0), str(Digit, 0, 0), str(Digit, 0, 0) }
#if (Mode = 0)
  #declare DialFile = concat("tex/dial_garage_", str(Lit, 0, 0), ".png")
#else
  #declare DialFile = concat("tex/dial_board_", str(Lit, 0, 0), ".png")
#end
#declare RC = 34;
#declare Keys = array[5] { -136, -68, 0, 68, 136 }

// chrome bezel and enamel face
superellipsoid { <0.14, 0.14> scale <226, 101, 10> translate <RC, 0, -2> texture { T_Chrome } }
superellipsoid { <0.14, 0.14> scale <216, 92, 4> translate <RC, 0, -12.5> texture { T_CaribDeep } }

// the dial, lit from behind, under glass, with a chrome surround
difference {
  superellipsoid { <0.2, 0.2> scale <198, 40, 4> translate <RC, 50, -18> }
  box { <RC - 190, 17, -40>, <RC + 190, 83, 0> }
  texture { T_Chrome }
}
box { <0, 0, 0>, <380, 66, 1>
      texture { pigment { image_map { png DialFile interpolate 2 } scale <380, 66, 1> } finish { ambient 0 emission 0.55 diffuse 0.6 } }
      translate <RC - 190, 17, -17> }
box { <RC - 190, 17, -21.5>, <RC + 190, 83, -21>
      texture { pigment { srgbf <1, 1, 1, 0.97> } finish { ambient 0 diffuse 0 specular 0.9 roughness 0.001 reflection 0.08 } } }
#if (Lit > 0)
  box { <-1.6, 0, 0>, <1.6, 30, 1> translate <RC + Keys[Lit - 1], 50, -19.5>
        texture { pigment { srgb <0.85, 0.08, 0.05> } finish { ambient 0 emission 0.2 specular 0.6 } } }
#end

// five piano keys in chrome slots
#for (I, 0, 4)
  #local X = RC + Keys[I];
  #local Down = (I + 1 = Lit);
  #local D = 26 - 16*Down;
  superellipsoid { <0.2, 0.2> scale <31, 32, 3> translate <X, -28, -17> texture { T_Chrome } }
  box { <X - 27, -58, -17.5>, <X + 27, 2, -16.5> pigment { srgb 0.02 } }
  union {
    superellipsoid { <0.12, 0.12> scale <26, 29, D/2> translate <X, -28, -17 - D/2>
                     texture { pigment { srgb <0.97, 0.93, 0.80> * (1 - 0.12*Down) } finish { ambient 0 diffuse 0.62 specular 0.8 roughness 0.004 reflection 0.05 } } }
    box { <X - 26, -1, -17 - D - 0.6>, <X + 26, 2.5, -17 - D + 2> texture { T_Chrome } }
    Hot(I + 1)
  }
  #if (Down)
    light_source { <X, -28, -40> srgb <1, 0.75, 0.3>*0.45 fade_distance 30 fade_power 2 }
  #end
#end

// knobs either side of the keys
#for (Sd, -1, 1, 2)
  union {
    cylinder { <0, 0, -12>, <0, 0, -30>, 16 texture { T_Chrome } }
    #for (A, 0, 350, 15)
      box { <-1.2, 15, -30>, <1.2, 17.2, -12> rotate z*A texture { T_Chrome } }
    #end
    cylinder { <0, 0, -30>, <0, 0, -31>, 10 texture { T_Bakelite } }
    translate <RC + Sd*192, -28, 0>
    #if (Sd < 0) Hot(HotKnobL) #else Hot(HotKnobR) #end
  }
#end

// the name in chrome script, as the car wears it
#declare Nm = text { ttf FontScript "DigiCarlo" 0.3, 0 }
#declare NMn = min_extent(Nm); #declare NMx = max_extent(Nm);
object { Nm translate -<(NMn.x + NMx.x)/2, (NMn.y + NMx.y)/2, 0> scale 24 translate <RC, -76, -19> texture { T_Chrome } }

// ---------------------------------------------------------------------------
// the counter and the starter
// ---------------------------------------------------------------------------

#declare KX = 372;
difference {
  superellipsoid { <0.25, 0.25> scale <96, 42, 14> translate <KX, 16, -4> }
  box { <KX - 80, -10, -40>, <KX + 80, 42, 0> }
  texture { T_Chrome }
}
box { <KX - 81, -11, 2>, <KX + 81, 43, 6> pigment { srgb 0.02 } }
union {
  #for (I, 0, 3)
    #local X = KX - 60 + I*40;
    cylinder { <X - 18, 16, 30>, <X + 18, 16, 30>, 34
               texture { pigment { srgb <0.93, 0.92, 0.88> * (I = 3) + <0.06, 0.06, 0.07> * (I < 3) } finish { ambient 0 diffuse 0.7 specular 0.4 roughness 0.02 } } }
    Label(Digits[I], FontDigits, 44, <X, 16, -4.5>, texture { pigment { srgb <0.95, 0.94, 0.9> * (I < 3) + <0.08, 0.08, 0.09> * (I = 3) } finish { ambient 0 diffuse 0.7 } })
  #end
  Hot(HotCounter)
}
// the plate under it
superellipsoid { <0.3, 0.3> scale <96, 15, 3> translate <KX, -56, -6> texture { T_Snow } }
Label("SHOTS WAITING", FontNunito, 17, <KX, -56, -10>, T_Ink)

#declare BX = 563;
// lit when there is something to put in the library; STOP while a job runs
#if (Go = 2) #declare StartText = "STOP"; #else #declare StartText = "START"; #end
#declare T_StartLabel = texture { pigment { srgb <1, 0.97, 0.9> } finish { ambient 0 diffuse 0.8 emission 0.25*(Go > 0) } }
union {
  torus { 58, 7 rotate x*90 translate <BX, 12, -10> texture { T_Chrome } }
  cylinder { <BX, 12, -4>, <BX, 12, -12>, 56 texture { T_Chrome } }
  sphere { 0, 52 scale <1, 1, 0.38> translate <BX, 12, -12>
           texture { #if (Go) pigment { srgb <0.98, 0.22, 0.14> } finish { ambient 0 emission 0.42 diffuse 0.6 specular 0.8 roughness 0.004 reflection 0.08 }
                     #else T_Red #end } }
  Label(StartText, FontCooper, 27, <BX, 12, -32>, T_StartLabel)
  Hot(HotStart)
}
#if (Go) light_source { <BX, 12, -60> srgb <1, 0.3, 0.2>*0.5 fade_distance 60 fade_power 2 } #end
superellipsoid { <0.3, 0.3> scale <64, 13, 3> translate <BX - 4, -80, -6> texture { T_Snow } }
Label("PUT IN LIBRARY", FontNunito, 12.5, <BX - 4, -80, -10>, T_Ink)
Screw(<BX + 64, 94, -18>) Screw(<BX + 64, -94, -18>)
