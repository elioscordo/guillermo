## Pipeline Enforcement Rules

1. **Absolute Completeness:** Fully articulate every shot block from the first to the last shot. No compression, truncation, or early exit.
2. **Parameter Rigidity:** Every entry under `*** Parameters:` must sit on its own line using exactly three asterisks (`***`). Never flatten to a single line or comma-separated syntax.
3. **Closed-Loop Validation:** Every identifier in `** Voice:`, `** Cast:`, or `** Props:` MUST have an exact string match in the global `# Locations`, `# Cast`, `# Props`, and `# Voices` dictionaries.
4. **Omit None and Empty Fields:** Never write a field whose value would be `"None"` or `0` or `0.0`. Omit it entirely. Only write fields that carry real values.

---

## Output Schema

# Shots
* Name: Shot_[N]
  * Shot Type: [voice | video | video_loop]
  * Prompt: [High-fidelity image prompt. Composition structure: [Camera Angle & Lens Focal Length] + [Location Perspective Context] + [Cast positioning within 3D depth planes, physical orientation to camera, interacting with Props] + [Directional lighting, matching cast highlights, and cast contact shadows mapped to the location environment]]  
  * Prompt Voice: [Parenthetical emotion + spoken text — omit if no speech]
  * Voice: [Cast Name | "Narrator" — omit if no voice]
  * Cast: [Name(s) separated by '|' — omit if no cast]
  * Props: [Name(s) separated by '|' — omit if no props]
  * Prompt Comic: [Depending of the shot type]
  * Video: [Camera/environment movement — omit if Shot Type is voice]
  * Location: [Must match a Location Name. Share locations]
  * Parameters:
    * Buffer In: [Float — voice only]
    * Buffer Out: [Float — voice only]
    * Duration: [Float — video and video_loop only]
    * Iterations: [Integer >= 1 — video_loop only]

## Shot Type Guide

### `voice`
Dialogue. Requires `Prompt`, `Prompt Voice`, `Buffer In`, `Buffer Out`.
For dialogue-over-background pair with `Prompt Voice`, `Voice`,`buffer in`,`buffer out`, `Duration` not longer required.
Use Prompt Video here specifically to direct camera positioning, framing adjustments, and subtle cast actions or facial expressions matching the dialogue.
**Cost = 1 coin.**

### `video`
Linear character actions or plot-driven movements. High value actions required by the narrative . Requires `Prompt`, `Video`, `Duration`.
For dialogue-over-background pair with `Prompt Voice`, `Voice`,`buffer in`,`buffer out`, `Duration` not longer required.
**Cost = 1 coin + duration seconds.**

### `video_loop`
Wide/establishing shots with ambient motion. Requires `Prompt`, `Video`, `Iterations`, `Duration`. Keep `Duration` low (2.0–3.0s) and use high `Iterations` to extend screen time for free. For dialogue-over-background pair with `Prompt Voice`, `Voice`,`buffer in`,`buffer out`, `Duration` and `Iterations` not longer required.
**Cost = 1 coin + duration seconds.**

### `caption`
Shot can be the in the first shots serves as a title, or if requested to introduce narrative elements  Requires `Prompt`, `Prompt Comic`, `Prompt Voice` `Buffer In`, `Buffer Out`
**Cost = 2 coin.**

### `comic`
Static no voice and video image for comic books. Requires `Prompt`  and `Prompt Comic` with the text and the speech bubble directioning. If all comic shots are required omit the voice sections
**Cost = 1 coin.**


# Locations
* Name: [Unique_Location_ID]
  * Prompt:
    #Environment:
        [describe the environment and its key features and details]
    #Visible Objects:
        [describe the visible objects and their details]
    #Lighting:
        [describe the lighting and its details]

# Cast
* Name: [Character_Name]
  * Prompt:
    #Age:
    #Features:
    #Clothing:
    #Core Look:
    #Context
    

# Props
* Name: [Prop_Name]
  * Prompt: [Material, size, texture, appearance]

# Voices
* Name: [Character_Name — must match Cast exactly]
  * Google Voice: [Voice ID]
  * Prompt:
    #Style:
    #Pace:
    #Accent:

# Change Log
* [Timestamp — math audit: Total Shots / Motion Shots / Video Seconds / Coin Spend]

# Comment
* [Rendering optimizations and coin economy notes]