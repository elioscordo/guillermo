## Pipeline Enforcement Rules

1. **Absolute Completeness:** Fully articulate every shot block from the first to the last shot. No compression, truncation, or early exit.
2. **Closed-Loop Validation:** Every identifier in `** Voice:`, `** Cast:`, or `** Props:` MUST have an exact string match in the global `# Locations`, `# Cast`, `# Props`, and `# Voices` dictionaries.
3. **Omit None and Empty Fields:** Never write a field whose value would be `"None"` or `0` or `0.0`. Omit it entirely. Only write fields that carry real values.
---

## Output Schema

# Shots
* Name: Shot_[N]
  * Prompt:
      #Framing & Proximity: [wide shot | full shot | mid shot | close shot] targeting [Primary Subject].
      #Spatial Relations: [Character A] is in the [foreground / midground / background], facing [direction]. [Character B] is [adjacent to / behind / facing / overlapping with] Character A. 
      #Location Framing: The camera captures the [upper / lower / wide panoramic / specific quadrant] view of the location, exposing the [specific structural elements or visible objects from the Location dictionary].
      #Subject Action: [Describe current pose, expression, or immediate static interaction].
  * Prompt Voice: [Parenthetical emotion + spoken text — omit if no speech]
  * Voice: [Cast Name | "Narrator" — omit if no voice]
  * Cast: [Name(s) separated by '|' — omit if no cast]
  * Props: [Name(s) separated by '|' — omit if no props]
  * Prompt Comic: [caption(...) for Shot_01, landmarks, and final shot — omit otherwise]
  * Video: [Camera/environment movement — omit if Shot Type is voice]
  * Location: [Must match a Location Name]
  * Parameters:
    *** Buffer In: [Float — voice only]
    *** Buffer Out: [Float — voice only]


# Locations
* Name: [ParentID_SubLocationID — e.g., Woods_Clearing or Woods_DeepThicket]
  * Prompt:
    #Global Environment: [Define the macro aesthetic to preserve continuity across all sub-locations. E.g., Dense Pacific Northwest forest, towering redwood trees, thick moss coating the ground, damp misty atmosphere].
    #Local Landmark: [The specific visual anchor for this sub-location. E.g., Centered around a rotting, hollowed-out fallen log / A small rocky clearing next to a trickling stream].
    #Visible Objects: [Specific props or natural elements unique to this exact spot. E.g., smooth river stones, wild ferns, patches of clover].
    #Lighting & Time: [Crucial for visual consistency. E.g., Dappled afternoon sunlight filtering through the dense canopy, soft golden hour beams, heavy shadows].

# Cast
* Name: [Character_Name]
  * Prompt:
    #Age:
    #Features:
    #Clothing:
    #Core Look:

# Props
* Name: [Prop_Name]
  * Prompt: [Material, size, texture, appearance]

# Voices
* Name: [Character_Name — must match Cast exactly]
  * Voice Name: [Prebuilt Voice ID from Gemini Library — e.g., Kore, Puck, Fenrir, Aoede]
  * Audio Profile:
    #Identity Description: [Establish the base physical and psychological vocal archetype, e.g., A gravelly, world-weary middle-aged explorer with a raspy undertone].
    #Director's Notes:
        * Style: [Natural language style description, e.g., Uses a vocal smile, leaking underlying amusement despite severe circumstances].
        * Pacing: [Tempo parameters, e.g., The tempo is measured and deliberate, with slight pauses between sentences for heavy breathing].
        * Accent: [Specific regional accent parameters, e.g., Modern British English accent as heard in Croydon, London].

# Change Log
* [Timestamp — math audit: Total Shots / Motion Shots / Video Seconds / Coin Spend]

# Comment
* [Rendering optimizations and coin economy notes]