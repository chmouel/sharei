BRAND_CSS = """
  .aniflow-brand {
    --aniflow-pink:#ff3bc8; --aniflow-cyan:#2feaff; --aniflow-violet:#8572ff;
    --aniflow-gold:#ffbd6b; --aniflow-ice:#e7f8ff; --aniflow-night:#13102c;
    display:block; width:min(100%, 46rem); margin:0 auto 30px;
    color:var(--aniflow-cyan); -webkit-tap-highlight-color:transparent;
  }
  .aniflow-brand svg { display:block; width:100%; height:auto; overflow:visible; }
  .aniflow-brand:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:6px; }
  .aniflow-brand .brand-plate { fill:var(--aniflow-night); stroke:color-mix(in srgb, var(--aniflow-violet) 48%, transparent); }
  .aniflow-brand .brand-grid { fill:none; stroke:var(--aniflow-cyan); stroke-width:1; opacity:.2; }
  .aniflow-brand .brand-rim { fill:none; stroke:var(--aniflow-pink); stroke-width:1; opacity:.65; }
  .aniflow-brand .brand-speed { fill:none; stroke-linecap:square; }
  .aniflow-brand .brand-extrusion { fill:var(--aniflow-pink); stroke:var(--aniflow-violet); stroke-width:2; }
  .aniflow-brand .brand-outline { fill:none; stroke:var(--aniflow-cyan); stroke-width:2; }
  .aniflow-brand .brand-chrome { fill:url(#aniflow-chrome); stroke:var(--aniflow-ice); stroke-width:1; stroke-linejoin:bevel; }
  .aniflow-brand .brand-star { fill:var(--aniflow-ice); filter:url(#aniflow-glow); transform-box:fill-box; transform-origin:center; }
  @media (prefers-reduced-motion:no-preference) {
    .aniflow-brand svg { transition:filter .2s; }
    .aniflow-brand .brand-star { transition:transform .4s; }
    .aniflow-brand:hover svg { filter:drop-shadow(0 0 9px color-mix(in srgb, var(--aniflow-pink) 26%, transparent)); }
    .aniflow-brand:hover .brand-star { transform:rotate(90deg); }
  }
"""

BRAND = """
<a class="aniflow-brand" href="/files/" aria-label="aniflow: browse files">
<svg viewBox="0 0 900 250" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="aniflow-chrome" x1="0" y1="0" x2="0" y2="110" gradientUnits="userSpaceOnUse">
      <stop stop-color="var(--aniflow-ice)"/>
      <stop offset=".22" stop-color="var(--aniflow-ice)"/>
      <stop offset=".46" stop-color="var(--aniflow-cyan)"/>
      <stop offset=".49" stop-color="var(--aniflow-night)"/>
      <stop offset=".52" stop-color="var(--aniflow-night)"/>
      <stop offset=".54" stop-color="var(--aniflow-ice)"/>
      <stop offset=".7" stop-color="var(--aniflow-pink)"/>
      <stop offset="1" stop-color="var(--aniflow-violet)"/>
    </linearGradient>
    <linearGradient id="aniflow-sunset" x2="0" y2="1">
      <stop stop-color="var(--aniflow-gold)"/>
      <stop offset=".5" stop-color="var(--aniflow-pink)"/>
      <stop offset="1" stop-color="var(--aniflow-violet)" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="aniflow-horizon">
      <stop stop-color="var(--aniflow-cyan)" stop-opacity="0"/>
      <stop offset=".3" stop-color="var(--aniflow-cyan)"/>
      <stop offset=".7" stop-color="var(--aniflow-pink)"/>
      <stop offset="1" stop-color="var(--aniflow-pink)" stop-opacity="0"/>
    </linearGradient>
    <filter id="aniflow-glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="3"/>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="aniflow-sun"><circle cx="723" cy="88" r="66"/></clipPath>
    <clipPath id="aniflow-plate"><path d="M22 12H878L898 32V218L878 238H22L2 218V32Z"/></clipPath>
    <g id="aniflow-letters" fill-rule="evenodd">
      <path d="M0 110 31 0H76L108 110H79L72 84H34L27 110ZM41 60H65L53 19Z"/>
      <path transform="translate(119)" d="M0 110V0H25L69 66V0H95V110H70L26 44V110Z"/>
      <path transform="translate(229)" d="M0 0H62V21H44V89H62V110H0V89H18V21H0Z"/>
      <path transform="translate(309)" d="M0 110V0H88V25H28V47H76V72H28V110Z"/>
      <path transform="translate(412)" d="M0 0H28V85H82V110H0Z"/>
      <path transform="translate(510)" d="M18 0H76L94 18V92L76 110H18L0 92V18ZM28 26V84H66V26Z"/>
      <path transform="translate(619)" d="M0 0H27L41 70L56 35L71 70L85 0H112L89 110H66L56 84L46 110H23Z"/>
    </g>
  </defs>
  <path class="brand-plate" d="M22 12H878L898 32V218L878 238H22L2 218V32Z"/>
  <g clip-path="url(#aniflow-plate)">
    <g clip-path="url(#aniflow-sun)">
      <circle cx="723" cy="88" r="66" fill="url(#aniflow-sunset)" opacity=".85"/>
      <path d="M650 83H796M650 96H796M650 112H796M650 131H796M650 153H796"
        fill="none" stroke="var(--aniflow-night)" stroke-width="6"/>
    </g>
    <path class="brand-grid" d="M0 165H900M0 180H900M0 202H900M0 232H900
      M450 165 0 250M450 165 145 250M450 165 280 250M450 165 390 250
      M450 165 510 250M450 165 620 250M450 165 755 250M450 165 900 250"/>
    <path d="M22 165H878" stroke="url(#aniflow-horizon)" stroke-width="2" filter="url(#aniflow-glow)"/>
    <path class="brand-rim" d="M24 25H244M24 25 15 34V83M876 225H654M876 225 885 216V167"/>
    <path class="brand-speed" d="M44 100H82M29 119H74M38 138H66" stroke="var(--aniflow-cyan)" stroke-width="4"/>
    <path class="brand-speed" d="M816 177H854M808 194H871" stroke="var(--aniflow-pink)" stroke-width="3"/>
  </g>
  <g transform="translate(112 72) skewX(-12) scale(.94)">
    <use class="brand-extrusion" href="#aniflow-letters" transform="translate(5 8)"/>
    <use class="brand-outline" href="#aniflow-letters" transform="translate(-2 -2)" opacity=".7"/>
    <use class="brand-chrome" href="#aniflow-letters"/>
  </g>
  <path d="M105 206H782" stroke="url(#aniflow-horizon)" stroke-width="3"/>
  <path class="brand-star" d="M259 49 262 61 274 64 262 67 259 79 256 67 244 64 256 61Z"/>
  <path class="brand-star" d="M795 146 797 154 805 156 797 158 795 166 793 158 785 156 793 154Z"/>
</svg>
</a>
"""
