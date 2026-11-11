// DigiCarlo - the Photo Board's ledge and what stands on it, shared by the
// board scene (full size) and the garage (shrunk to the board there).
//
// In the board scene's units: the ledge's top is at y = 0, the board's face
// at z = 4, and x = 0 is the middle of the board. Each tool is declared on
// its own, standing where it goes, so a scene can make each a hotspot.
//
// Needs from the including scene: T_Red, T_Chrome, T_Brass, the T_Plank
// macro and its seed S, and metropolitan.inc already included (for the toy).
// Reads Trash (left-out prints in the wastebasket).

#ifndef (Trash) #declare Trash = 0; #end
#ifndef (T_Black)
  #declare T_Black = texture { pigment { srgb <0.10, 0.10, 0.12> } finish { ambient 0 diffuse 0.6 specular 0.5 roughness 0.01 } }
#end
#declare LedgeHalf = 358;      // half its length

// the shelf itself, and the board along its front where the tags are pinned
#declare LedgeShelf = union {
  box { <-LedgeHalf, -14, -64>, <LedgeHalf, 0, 12> T_Plank(S, <0.86, 0.60, 0.36>, y*90) }
  box { <-LedgeHalf, -34, -66>, <LedgeHalf, -14, -58> T_Plank(S, <0.72, 0.47, 0.27>, y*90) }
}

// a date stamp; the program shows on its face the date it will stamp
#declare LedgeStamp = union {
  box { <-22, 0, -12>, <22, 10, 12> texture { T_Black } }
  box { <-18, 10, -8>, <18, 34, 8> texture { T_Black } }
  box { <-15, 14, -8.4>, <15, 26, -8> texture { pigment { srgb <0.14, 0.14, 0.16> } finish { ambient 0 diffuse 0.6 specular 0.3 roughness 0.02 } } }
  cylinder { <0, 34, 0>, <0, 44, 0>, 5 T_Plank(S, <0.55, 0.33, 0.17>, x*90) }
  sphere { <0, 52, 0>, 12 scale <1, 0.8, 1> T_Plank(S, <0.60, 0.35, 0.18>, x*90) }
  translate <-166, 0, -30>
}

// an alarm clock: the camera's own clock
#declare LedgeClock = union {
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
  translate <-60, 27, -30>
}

// an eraser: back to automatic
#declare LedgeEraser = union {
  superellipsoid { <0.2, 0.2> scale <18, 8, 9> translate <-10, 0, 0> texture { pigment { srgb <1.0, 0.63, 0.70> } finish { ambient 0 diffuse 0.8 specular 0.2 roughness 0.05 } } }
  superellipsoid { <0.2, 0.2> scale <12, 8, 9> translate <18, 0, 0> texture { pigment { srgb <0.45, 0.68, 0.92> } finish { ambient 0 diffuse 0.8 specular 0.2 roughness 0.05 } } }
  rotate z*8 rotate y*-15 translate <62, 9, -32>
}

// a wastebasket: leave out. Crumpled prints in it while any are left out.
#declare LedgeBin = union {
  difference {
    cone { <0, 0, 0>, 17, <0, 46, 0>, 22 }
    cone { <0, 2, 0>, 15.5, <0, 47, 0>, 20.5 }
    #for (A, 0, 350, 20)
      box { <-1.2, 8, -30>, <1.2, 38, 0> rotate y*A }
    #end
    texture { pigment { srgb <0.62, 0.66, 0.70> } finish { ambient 0 diffuse 0.4 specular 0.8 roughness 0.006 metallic reflection 0.25 } }
  }
  torus { 22, 1.6 translate <0, 46, 0> texture { T_Chrome } }
  #if (Trash)
    #local T_Crumpled = texture {
      pigment { bozo turbulence 0.6 color_map { [0 srgb <0.97, 0.96, 0.92>] [0.55 srgb <0.94, 0.93, 0.88>]
                                                [0.7 srgb <0.62, 0.80, 0.94>] [0.85 srgb <0.45, 0.72, 0.36>] [1 srgb <0.97, 0.96, 0.92>] } scale 4 }
      normal { crackle 1.4 scale 3.5 }
      finish { ambient 0 diffuse 0.8 specular 0.15 roughness 0.04 } }
    sphere { 0, 10 scale <1, 0.85, 0.95> texture { T_Crumpled } rotate <20, 40, 10> translate <-7, 43, 2> }
    sphere { 0, 9 scale <1, 0.9, 1> texture { T_Crumpled translate 7 } rotate <-10, 70, 30> translate <8, 45, -3> }
    sphere { 0, 8 scale <0.95, 0.85, 1> texture { T_Crumpled translate 13 } rotate <40, 10, -20> translate <1, 47, 10> }
  #end
  translate <185, 0, -30>
}

// the red-eye pen: a felt pen for dabbing red eyes on prints, 1990s style,
// lying on the ledge with its cap off beside it
#declare LedgePen = union {
  union {
    cylinder { <-30, 0, 0>, <18, 0, 0>, 4.6 texture { pigment { srgb 0.07 } finish { ambient 0 diffuse 0.5 specular 0.8 roughness 0.004 reflection 0.06 } } }
    cylinder { <-14, 0, 0>, <8, 0, 0>, 4.7 texture { pigment { srgb <0.97, 0.96, 0.92> } finish { ambient 0 diffuse 0.8 specular 0.3 } } }
    cylinder { <-11, 0, 0>, <5, 0, 0>, 4.75 texture { T_Red } }
    sphere { <18, 0, 0>, 4.6 scale <0.5, 1, 1> translate <9, 0, 0> texture { pigment { srgb 0.07 } finish { ambient 0 diffuse 0.5 specular 0.8 roughness 0.004 } } }
    cone { <-30, 0, 0>, 4.6, <-38, 0, 0>, 1.8 texture { pigment { srgb 0.07 } finish { ambient 0 diffuse 0.5 specular 0.8 roughness 0.004 } } }
    cone { <-38, 0, 0>, 1.8, <-43, 0, 0>, 0.7 texture { pigment { srgb <0.35, 0.05, 0.06> } finish { ambient 0 diffuse 0.9 } } }
    rotate y*28 translate <262, 4.6, -40>
  }
  union {
    cylinder { <0, 0, 0>, <17, 0, 0>, 5.2 texture { T_Red } }
    sphere { <17, 0, 0>, 5.2 scale <0.45, 1, 1> translate <9.35, 0, 0> texture { T_Red } }
    box { <2, 4.6, -1.1>, <18, 6.4, 1.1> texture { T_Chrome } }
    rotate x*90 rotate y*-12 translate <300, 5.2, -34>
  }
}

// the way back to the garage: a die-cast Metropolitan, nosing out to the left
#declare LedgeToy = object {
  MetropolitanToy
  translate <-195, 0, 0> rotate y*-25 scale 0.2
  translate <-268, 0, -32>
}
