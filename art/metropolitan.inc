// A 1956-58 Nash Metropolitan 1500 hardtop (Series III), after photographs:
// the "bathtub" body with high round front fenders carrying the headlights,
// fully enclosed front wheels, a wide oval mesh grille, the stainless spear
// that splits the two-tone in a Z down the door, a white roof, a one-piece
// curved windshield, whitewalls and dog-dish hubcaps.
//
// Real size, in centimetres: 380 long, 156 wide, 138 high, 216 between the
// axles. The front is at x = 0 and the car runs toward +x; y is up from the
// ground, z across (the driver's side, -z, is the one a viewer at the front
// left sees).
//
// Needs from the including scene: T_Chrome, and the Hot() macro. Declares
// Metropolitan, and reads HotLights and HotCar (numbers for Hot), Beams
// (headlights on), Paint and Contrast (the two colours).

#ifndef (Beams) #declare Beams = 0; #end
#ifndef (Paint) #declare Paint = srgb <0.18, 0.64, 0.73>; #end         // Caribbean Blue
#ifndef (Contrast) #declare Contrast = srgb <0.95, 0.93, 0.86>; #end   // Snowberry White

#declare F_CarPaint = finish { ambient 0 diffuse 0.62 specular 0.7 roughness 0.004
                               reflection { 0.04, 0.22 fresnel on } conserve_energy }

// -- the body, as a distance field: rounded shapes blended together -----------

#declare f_rbox = function(x, y, z, hx, hy, hz, r) {
  sqrt(pow(max(abs(x) - (hx - r), 0), 2) + pow(max(abs(y) - (hy - r), 0), 2)
       + pow(max(abs(z) - (hz - r), 0), 2)) - r
  + min(max(abs(x) - (hx - r), max(abs(y) - (hy - r), abs(z) - (hz - r))), 0)
}
#declare f_ell = function(x, y, z, rx, ry, rz) {
  (sqrt(pow(x / rx, 2) + pow(y / ry, 2) + pow(z / rz, 2)) - 1) * min(rx, min(ry, rz))
}
#declare f_smin = function(a, b, k) { min(a, b) - pow(max(k - abs(a - b), 0), 2) / (4 * k) }
#declare f_smax = function(a, b, k) { max(a, b) + pow(max(k - abs(a - b), 0), 2) / (4 * k) }

// a pontoon fender: a cylinder along x, its ends rounded off
#declare f_pontoon = function(x, y, z, x0, x1, r) {
  f_smax(sqrt(y * y + z * z) - r, abs(x - (x0 + x1) / 2) - (x1 - x0) / 2, 9)
}
// the tub, the belt line and the fenders
#declare f_lower = function(x, y, z) {
  f_smin(
    f_smin(f_rbox(x - 190, y - 50, z, 185, 28, 75, 20),                          // tub
           f_rbox(x - 255, y - 72, z, 123, 22, 74, 15), 12),                     // sides up to the belt
    f_smin(f_pontoon(x, y - 72, abs(z) - 54, 0, 150, 21),                         // front fenders
           f_pontoon(x, y - 66, abs(z) - 54, 232, 374, 22), 10), 12)             // rear fenders
}
// the hood, rising toward the windshield between the fenders
#declare f_hood = function(x, y, z) {
  f_rbox(x - 82, y - 70 - 0.065 * (x - 82), z, 78, 12, 47, 11)
}
// the hardtop's cabin: an upright windshield and rear window, sides leaning in
#declare f_cabin = function(x, y, z) {
  f_smax(
    f_smax(f_rbox(x - 230, y - 112, z * (1 + max(y - 95, 0) * 0.004), 74, 26, 62, 20),
           -0.83 * (x - 160) + 0.56 * (y - 93), 7),
    0.80 * (x - 304) + 0.60 * (y - 100), 7)
}
#declare f_shell = function(x, y, z) {
  f_smin(f_smin(f_lower(x, y, z), f_hood(x, y, z), 16), f_cabin(x, y, z), 6)
}
// cut out: the wheel openings (the front ones only below the fender skirt)
// and the grille's oval mouth
#declare f_openings = function(x, y, z) {
  min(min(f_smax(sqrt(pow(x - 70, 2) + pow(y - 31, 2)) - 35, y - 44, 4),
          f_smax(sqrt(pow(x - 286, 2) + pow(y - 31, 2)) - 36, y - 45, 4)),
      f_smax(sqrt(pow(max(abs(z) - 31, 0), 2) + pow(y - 53, 2)) - 13, x - 13, 2))
}
#declare f_body = function(x, y, z) { f_smax(f_shell(x, y, z), -f_openings(x, y, z), 3) }

// where the two-tone divides: at the headlights along the front fender, down
// across the door in the Z, and low along the rear quarter
#declare f_divide = function(x) {
  select(x - 132, 66, select(x - 176, 66 - (x - 132) * 16 / 44, 50))
}

// the windows: < 0 inside one. The windshield wraps round its corners; the
// door and rear quarter windows have a slim pillar between them.
#declare f_box3 = function(x, y, z, hx, hy, hz) { max(abs(x) - hx, max(abs(y) - hy, abs(z) - hz)) }
#declare f_windows = function(x, y, z) {
  min(min(f_box3(x - 180, y - 116, z, 22, 19, 55),                    // windshield
          f_box3(x - 226, y - 116, abs(z) - 60, 19, 16, 22)),         // door windows
      min(f_box3(x - 266, y - 114, abs(z) - 60, 16, 14, 22),          // rear quarters
          f_box3(x - 300, y - 117, z, 16, 17, 47)))                    // rear window
}

#declare T_Glass = texture { pigment { srgb <0.05, 0.08, 0.10> }
                             finish { ambient 0 diffuse 0.2 specular 0.95 roughness 0.001
                                      reflection { 0.12, 0.45 fresnel on } } }
#declare T_Paint2 = texture {
  // the roof white; the colour above the spear; white below
  pigment {
    function { select(y - 97, select(y - f_divide(x), 0, 1), 0) }
    color_map { [0 Contrast] [0.5 Contrast] [0.5 Paint] [1 Paint] }
  }
  finish { F_CarPaint }
}

#declare Body = isosurface {
  function { f_body(x, y, z) }
  contained_by { box { <-20, 16, -82>, <385, 145, 82> } }
  max_gradient 2.2
  accuracy 0.005
  texture {
    function { select(y - 97, 0, select(f_windows(x, y, z), 1, 0)) }
    texture_map { [0 T_Paint2] [0.5 T_Paint2] [0.5 T_Glass] [1 T_Glass] }
  }
}

#macro OnBody(X, Y, Side)
  // the point on the body's side (Side = -1 or 1) at X, Y
  trace(Body, <X, Y, Side * 120>, <0, 0, -Side>)
#end
#macro OnFront(Y, Z)
  trace(Body, <-60, Y, Z>, <1, 0, 0>)
#end

#declare T_Rubber = texture { pigment { srgb 0.06 } finish { ambient 0 diffuse 0.6 specular 0.1 roughness 0.06 } }
#declare T_White = texture { pigment { srgb <0.96, 0.95, 0.91> } finish { ambient 0 diffuse 0.8 specular 0.2 } }
#declare T_Mesh = texture { pigment { srgb 0.035 } finish { ambient 0 diffuse 0.5 } }

// -- lamps, grille, bumper -------------------------------------------------------

#declare HeadL = OnFront(74, -54);
#declare HeadR = OnFront(74, 54);
#macro Headlight(P)
  union {
    torus { 10.2, 1.9 rotate z*90 translate P + <-0.8, 0, 0> texture { T_Chrome } }
    difference {
      cylinder { P + <-1, 0, 0>, P + <8, 0, 0>, 12 }
      cylinder { P + <-3, 0, 0>, P + <6, 0, 0>, 9.6 }
      texture { T_Chrome }
    }
    sphere { 0, 9.4 scale <0.36, 1, 1> translate P + <0.6, 0, 0>
      texture {
        #if (Beams)
          pigment { srgb <1, 0.97, 0.86> } finish { ambient 0 emission 1.4 diffuse 0.3 }
        #else
          pigment { srgb <0.93, 0.95, 0.96> }
          finish { ambient 0 emission 0.08 diffuse 0.35 specular 0.95 roughness 0.001 reflection 0.35 }
        #end
      }
      #if (Beams) no_shadow #end
    }
    Hot(HotLights)
  }
  #if (Beams)
    light_source { P + <-6, 0, 0> srgb <1, 0.95, 0.82> * 1.8
                   // at the floor ahead and to the left, where it meets the room
                   // between the car and the darkroom door, clear of the bench
                   spotlight point_at <-100, 0, 100 + P.z * 0.6> radius 8 falloff 19 tightness 6
                   fade_distance 240 fade_power 1.6 }
  #end
#end

#macro ParkingLight(P)
  union {
    torus { 3.6, 0.8 rotate z*90 translate P + <-0.6, 0, 0> texture { T_Chrome } }
    sphere { 0, 3.2 scale <0.5, 1, 1> translate P
             texture { pigment { srgb <1, 0.9, 0.7> }
                       finish { ambient 0 emission 0.12 diffuse 0.5 specular 0.9 roughness 0.002 } } }
  }
#end

// the grille: a chrome oval round an egg-crate mesh, the M in the middle
#declare GrilleOval = union {
  cylinder { <-5, 53, -31>, <20, 53, -31>, 13 }
  cylinder { <-5, 53, 31>, <20, 53, 31>, 13 }
  box { <-5, 40, -31>, <20, 66, 31> }
}
#declare Grille = union {
  sphere_sweep {
    linear_spline 27,
    #for (A, 0, 180, 15)
      <7.5, 53 + 13.4 * cos(radians(A)), 31 + 13.4 * sin(radians(A))>, 1.5
    #end
    #for (A, 180, 360, 15)
      <7.5, 53 + 13.4 * cos(radians(A)), -31 + 13.4 * sin(radians(A))>, 1.5
    #end
    <7.5, 66.4, 31>, 1.5
    texture { T_Chrome }
  }
  intersection {
    union {
      #for (Z, -44, 44, 4.2)
        box { <9.5, 38, Z - 0.35>, <12.5, 68, Z + 0.35> }
      #end
      #for (Y, 41.2, 66, 4.2)
        box { <9.5, Y - 0.35, -45>, <12.5, Y + 0.35, 45> }
      #end
    }
    object { GrilleOval }
    texture { T_Chrome }
  }
  intersection { box { <12.5, 38, -46>, <14, 68, 46> } object { GrilleOval } texture { T_Mesh } }
  cylinder { <6.2, 53, 0>, <9.5, 53, 0>, 5.6 texture { T_Chrome } }
  #declare Mt = text { ttf FontCooper "M" 0.4, 0 }
  object { Mt translate -<(min_extent(Mt).x + max_extent(Mt).x) / 2, (min_extent(Mt).y + max_extent(Mt).y) / 2, 0>
           scale 7 rotate y*90 translate <5.9, 53, 0>
           texture { pigment { srgb <0.8, 0.12, 0.1> } finish { ambient 0 diffuse 0.7 specular 0.6 } } }
}

// the bumper: a chrome blade wrapping the nose, two overriders, the plate
#declare Bumper = union {
  sphere_sweep {
    cubic_spline 9,
    <44, 0, -78>, 5.5, <30, 0, -76>, 5.5, <8, 0, -72>, 5.5, <-4, 0, -48>, 5.5, <-7, 0, 0>, 5.5,
    <-4, 0, 48>, 5.5, <8, 0, 72>, 5.5, <30, 0, 76>, 5.5, <44, 0, 78>, 5.5
    scale <1, 1.25, 1>
    translate <0, 34, 0>
    texture { T_Chrome }
  }
  #for (S, -1, 1, 2)
    superellipsoid { <0.5, 0.35> scale <4.5, 15, 3.4> translate <-9.5, 41, S * 24> texture { T_Chrome } }
  #end
  box { <0, 0, -0.3>, <30, 15, 0.3> texture { pigment { image_map { png "tex/plate.png" interpolate 2 } scale <30, 15, 1> }
                                               finish { ambient 0 diffuse 0.8 specular 0.3 } }
        rotate y*90 translate <-12.8, 36.5, 15> }
}

// a wheel: whitewall tyre, painted rim, dog-dish hubcap with the M
#macro Wheel(P, Side)
  union {
    torus { 23.5, 8.4 rotate x*90 texture { T_Rubber } }
    difference {
      cylinder { <0, 0, 0>, <0, 0, Side * 8.2>, 27.2 }
      cylinder { <0, 0, -1>, <0, 0, Side * 9>, 17.5 }
      texture { T_White }
    }
    cylinder { <0, 0, 0>, <0, 0, Side * 7.6>, 17.6 texture { pigment { Paint } finish { F_CarPaint } } }
    sphere { 0, 13.5 scale <1, 1, 0.34> translate <0, 0, Side * 8.2> texture { T_Chrome } }
    cylinder { <0, 0, Side * 12>, <0, 0, Side * 12.7>, 2.6
               texture { pigment { srgb <0.8, 0.12, 0.1> } finish { ambient 0 diffuse 0.7 specular 0.5 } } }
    translate P
  }
#end

// the stainless spear along the two-tone line, found on the body's side
#macro Spear(Side)
  sphere_sweep {
    linear_spline 34,
    #for (I, 0, 33)
      #local X = 16 + I * 10.4;
      #local Y = f_divide(X);
      #local P = OnBody(X, Y, Side);
      P + <0, 0, Side * 0.5>, 1.05
    #end
    texture { T_Chrome }
  }
#end

#declare Metropolitan = union {
  object { Body }
  Headlight(HeadL)
  Headlight(HeadR)
  ParkingLight(OnFront(61, -54) + <-0.4, 0, 0>)
  ParkingLight(OnFront(61, 54) + <-0.4, 0, 0>)
  object { Grille }
  object { Bumper }
  Spear(-1)
  Spear(1)
  // the hood ornament
  union {
    sphere { 0, 3 scale <4, 0.9, 0.9> }
    cone { <6, 0, 0>, 1.8, <14, 3.5, 0>, 0.3 }
    texture { T_Chrome }
    translate trace(Body, <12, 200, 0>, <0, -1, 0>) + <2, 0.8, 0>
  }
  // the driver's mirror on the fender
  union {
    cylinder { <0, 0, 0>, <0, 9, 0>, 0.7 }
    sphere { <0, 10, 0>, 3.4 scale <0.5, 1, 1> }
    texture { T_Chrome }
    translate OnBody(128, 86, -1) + <0, -1, 2>
  }
  // a door handle each side
  #for (S, -1, 1, 2)
    box { <-4.5, -0.7, 0>, <4.5, 0.7, S * 1.4> texture { T_Chrome } translate OnBody(236, 88, S) }
  #end
  // the back: a bumper, tail lights, and the spare in its continental cover
  sphere_sweep {
    cubic_spline 7,
    <330, 0, -80>, 5, <350, 0, -77>, 5, <380, 0, -66>, 5, <386, 0, 0>, 5, <380, 0, 66>, 5,
    <350, 0, 77>, 5, <330, 0, 80>, 5
    scale <1, 1.2, 1> translate <0, 36, 0>
    texture { T_Chrome }
  }
  #for (S, -1, 1, 2)
    sphere { 0, 4.5 scale <0.5, 1, 1> translate trace(Body, <460, 66, S * 56>, <-1, 0, 0>)
             texture { pigment { srgb <0.85, 0.08, 0.06> } finish { ambient 0 emission 0.15 specular 0.8 roughness 0.003 } } }
  #end
  union {
    torus { 22, 9 rotate z*90 texture { pigment { Paint } finish { F_CarPaint } } }
    cylinder { <-6, 0, 0>, <6, 0, 0>, 22 texture { pigment { Paint } finish { F_CarPaint } } }
    torus { 29.5, 1.8 rotate z*90 texture { T_Chrome } }
    cylinder { <5.5, 0, 0>, <7, 0, 0>, 7 texture { T_Chrome } }
    translate <394, 62, 0>
  }
  Wheel(<70, 31.5, -60>, -1)
  Wheel(<70, 31.5, 60>, 1)
  Wheel(<286, 31.5, -60>, -1)
  Wheel(<286, 31.5, 60>, 1)
}
