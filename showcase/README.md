# Aegis Sentinel showcase

An isolated public website. The operational React application, backend, inference services, databases and model weights are not part of this build.

## Run

```
cd showcase
npm ci
npm run dev
npm run build
```

Vite writes a static multi page site into `dist/`. The pages use clean URLs on Vercel. `vercel.json` belongs with the build output for direct static deployments. A future Git connected Vercel project should use `showcase` as its root, `npm run build` as the build command, and `dist` as the output directory.

## Experience

The homepage uses locally bundled GSAP ScrollTrigger and Lenis. Desktop includes a pinned observation book with four distinct spreads and paper fold transitions. Mobile uses a vertically composed book with named chapter controls and horizontal swipe navigation. Reduced motion removes smooth scrolling and long pins. Document transitions use the native browser API with a short fallback. Native dialogs provide menu focus containment and source inspection. The drone recurs through the hero, skyline, capture, flight passage, aerial chapter and finale. See `docs/CHOREOGRAPHY_RESEARCH.md` for the research and motion contract.

Images and the Archivo variable font are served locally. Responsive photo derivatives are selected through `srcset`. See `docs/assets.json` for image origins, usage boundaries and the font license.

## Account service boundary

Login and signup are complete visual pages. Account services are deliberately not connected in this public static deployment. Fields are disabled; credentials are not collected, transmitted or persisted. The existing operational app remains the home of real authentication.

## Product representation

Aerial operations are simulated. Editorial city photographs do not represent footage captured or analyzed by Aegis. No synthetic detections, performance numbers, customer claims or screenshots are presented as product evidence.
