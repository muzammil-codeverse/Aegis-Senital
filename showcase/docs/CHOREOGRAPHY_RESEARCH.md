# Aegis Sentinel: observation book and recurring protagonist

Research and implementation revision, 18 October 2026.

## Diagnosis

The first version varied photographs but repeated its grammar: large heading, parallax photograph, horizontal cards, another heading. The drone disappeared after the opening. This revision changes the spatial relationship between scenes and makes the drone a recurring physical actor.

## References and evidence

| Reference                                                                                                     | Evidence reviewed                                                                       | Useful principle                                                                           | Aegis adaptation                                                                   |
| ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| [Lenis](https://lenis.dev/)                                                                                   | Live opening and scrolled composition; official showcase                                | Typography and foreground imagery need different movement and pacing                       | Countermoving passage typography, one scroll clock, independent drone movement     |
| [Igloo Inc case study](https://www.awwwards.com/igloo-inc-case-study.html)                                    | Creator's published process                                                             | The creators replaced similar project objects with distinct forms after testing repetition | Each book chapter has its own artwork, paper treatment and editorial composition   |
| [David Whyte Experience](https://www.awwwards.com/case-study-david-whyte-experience-by-immersive-garden.html) | Creator's case study                                                                    | The reveal takes its character from the material and subject                               | Paper folding and photographic discovery rather than a generic slide transition    |
| [My Little Storybook](https://www.awwwards.com/sites/my-little-storybook)                                     | Awwwards record and official experiment description; live visit reached a loading state | A physical narrative container can organize progression                                    | A four chapter observation book with visible binding, folios and direct navigation |
| [The Boat](https://www.awwwards.com/sites/the-boat)                                                           | Awwwards record                                                                         | Illustrated storytelling can use photography scale and layered movement                    | Different movement roles for foreground drone, environment and text                |
| [Siena Film Foundation](https://siena.film/)                                                                  | Live instruction layer and entrance; Awwwards case study fetch timed out                | An authored experience needs orientation and ways to navigate                              | The book supports scrolling, named tabs, arrows and keyboard navigation            |

Live inspection and published descriptions are distinguished here. No performance measurements or runtime behavior of inaccessible scenes are claimed. The published WebGL approaches are references for composition, not dependencies imported into Aegis.

## The revised sequence

1. The drone hovers higher in the existing mineral hero. Its position responds subtly to the mouse. Scrolling translates and reduces the entire stage.
2. A smaller drone passes across the skyline, moving separately from the environmental photograph.
3. The camera approach contracts the drone while a circular photographic aperture expands.
4. A new flight passage crosses a drawn path between countermoving lines of typography.
5. The observation book becomes the central interactive object: View, Altitude, Context and Judgment. Each turn folds around the binding using scale and skew in two dimensions. The Altitude chapter includes the drone.
6. Human review slows the pacing with sequential sentence emphasis and source inspection.
7. The drone returns over the city in the finale. The footer signature reveals from its baseline.

## Motion contract

The existing GSAP and Lenis dependencies remain. No canvas renderer, 3D model, video sequence or new image download is required. The desktop book pin is limited to sufficiently wide and tall viewports. Phones receive a vertically composed spread with explicit chapter controls and horizontal swipe detection that preserves vertical scrolling. Reduced motion removes idle flight, smoothing, pinning and page folds, retaining direct chapter selection.

A chapter state machine keeps the last requested destination when navigation happens during a turn. Only the active spread is exposed to assistive technology and keyboard focus. Previous and next states stop at the first and last chapter; arrow keys, Home and End operate the tab list.

## Revision: continuity, paper and distinct routes

The earlier version repeated the drone asset in six independent scenes. It also simulated a page fold with a horizontal scale transform. Those implementation choices explained the visible lack of continuity and paper depth.

### Additional references inspected

| Reference | What was verified | Applied decision |
| --- | --- | --- |
| [StPageFlip](https://nodlik.github.io/StPageFlip/) and its [source](https://github.com/Nodlik/StPageFlip) | Official documentation and live HTML example, including next page interaction. Soft leaves support corner geometry, clipped reverse surfaces and moving shadows. | Replace the scale fold with eight soft HTML leaves. Keep chapter selection, previous and next controls, keyboard access and portrait mode. No model or WebGL scene. |
| [BookBlock, Codrops](https://tympanus.net/codrops/2012/09/03/bookblock-a-content-flip-plugin/) | Original implementation article describes separate surfaces and shadow overlays. | Paper needs to cross a binding and reveal the next surface. Merely exchanging images halfway through a scale animation is insufficient. |
| [Gianluca Gradogna portfolio](https://gianlucagradogna.com/) and [creator case study](https://tympanus.net/codrops/2025/01/30/case-study-gianluca-gradogna-portfolio-25/) | Live split composition, image layers and photography navigation; creator describes position, opacity and clip masks as core techniques. The screenshots show contrasting editorial treatments within one visual identity. | Build separate compositions for system, mission and evidence. Carry the shared palette and typography across them. Use a paired shutter for route departures and arrivals. |
| [Cyd Stumpel transition selection, Awwwards](https://www.awwwards.com/inspiration/default-page-transition-cyd-stumpel-portfolio-2025) | Search listing identifies a View Transition API example. The page fetch timed out. Timing and live interaction were not verified. | Technical context only. No claims about measured runtime or copied timings. |

### Revised sequence

The homepage has one drone image node. That same node moves into a fixed flight layer. A single measured path interpolates its position, scale and bank through every section, in both scroll directions. No scene swaps, opacity handoffs or cloned drone images are used. The hero sits higher and uses a two line composition. Motion preferences return the original element to a static hero.

The book now reads as paper, with eight leaves and four chapters. It is intentionally controlled by the reader rather than automatically forcing page turns during a pinned scroll. Mobile uses individual leaves so typography remains readable. Buttons and keyboard navigation use the same page engine as direct corner dragging. Reduced motion chapter selection changes pages immediately.

Platform is an image atlas, an assembly of three signals, and an interactive relationship orbit. Operations is an aerial opening followed by a vertical mission itinerary, a planning sheet, a framed panorama and a return contact sheet. Intelligence is a fanned archive, selectable source inspection and a reasoning sequence ending in a large human decision statement. They no longer share alternating editorial blocks.

The route transition closes two panels around the destination name, then opens onto the new document. It works across the actual static routes, retains normal modified clicks, and clears itself after browser back navigation. Reduced motion keeps ordinary document navigation.
