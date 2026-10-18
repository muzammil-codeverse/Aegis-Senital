import streetImage from "./assets/street.webp";
import cityImage from "./assets/city.webp";
import observationImage from "./assets/observation.webp";
import architectureImage from "./assets/architecture.webp";
import nightImage from "./assets/night.webp";
export function initSceneTransitions({ gsap, reduced, getLenis }) {
  const curtain = document.createElement("div");
  curtain.className = "route-shutter";
  curtain.setAttribute("aria-hidden", "true");
  curtain.innerHTML = "<i></i><i></i><span></span>";
  document.body.append(curtain);
  const panels = curtain.querySelectorAll("i"),
    label = curtain.querySelector("span");
  let arriving;
  try {
    arriving = sessionStorage.getItem("aegis:arrival");
    sessionStorage.removeItem("aegis:arrival");
  } catch {}
  const clear = () => {
    gsap.set(curtain, { visibility: "hidden" });
    gsap.set(panels, { scaleX: 0 });
    gsap.set(label, { opacity: 0 });
    gsap.set("main", { clearProps: "transform,opacity" });
    document.documentElement.classList.remove("route-arrival");
  };
  if (arriving && !reduced.matches) {
    label.textContent = arriving;
    gsap.set(curtain, { visibility: "visible" });
    gsap.set(panels, { scaleX: 1 });
    gsap.set(label, { opacity: 1 });
    document.documentElement.classList.remove("route-arrival");
    Promise.race([
      document.fonts.ready,
      new Promise((resolve) => setTimeout(resolve, 450)),
    ]).then(() => {
      gsap
        .timeline({ onComplete: clear })
        .to(label, { y: -20, opacity: 0, duration: 0.3 }, 0.05)
        .to(
          panels,
          { scaleX: 0, duration: 0.85, stagger: 0.055, ease: "power4.inOut" },
          0.1,
        )
        .fromTo(
          "main",
          { y: 35 },
          { y: 0, duration: 1, ease: "power3.out" },
          0.1,
        );
    });
  } else clear();
  let navigating = false;
  document.querySelectorAll("a[href]").forEach((a) =>
    a.addEventListener("click", (e) => {
      if (
        e.defaultPrevented ||
        e.button !== 0 ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey ||
        a.target === "_blank" ||
        a.hasAttribute("download") ||
        reduced.matches
      )
        return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.pathname === location.pathname)
        return;
      e.preventDefault();
      if (navigating) return;
      navigating = true;
      document.querySelector("dialog[open]")?.close();
      getLenis()?.stop();
      const names = {
        platform: "Platform",
        operations: "Operations",
        intelligence: "Intelligence",
        technology: "Technology",
        login: "Welcome back",
        signup: "Your perspective",
        privacy: "Privacy",
      };
      const destination =
        names[url.pathname.replace(/^\//, "").replace(/\.html$/, "")] ||
        "Aegis Sentinel";
      label.textContent = destination;
      gsap.set(label, { y: 20 });
      gsap.set(curtain, { visibility: "visible" });
      gsap
        .timeline({
          onComplete: () => {
            try {
              sessionStorage.setItem("aegis:arrival", destination);
            } catch {}
            location.assign(url.href);
          },
        })
        .to(
          panels,
          { scaleX: 1, duration: 0.65, stagger: 0.045, ease: "power4.inOut" },
          0,
        )
        .to("main", { scale: 0.975, duration: 0.7, ease: "power2.inOut" }, 0)
        .to(
          label,
          { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" },
          0.4,
        );
    }),
  );
  addEventListener("pageshow", (e) => {
    if (e.persisted) {
      clear();
      navigating = false;
      getLenis()?.start();
    }
  });
}

export function initEditorialMotion({ gsap, ScrollTrigger, reduced }) {
  const orbital = [
    [
      "The source",
      "Return to the original media. A model output begins a question, it does not close it.",
      streetImage,
    ],
    [
      "The place",
      "Locate an observation within a wider setting. Spatial context connects a frame to its surroundings.",
      cityImage,
    ],
    [
      "The evidence",
      "Gather attachments and notes in a case. Keep the reasoning and original material together.",
      observationImage,
    ],
    [
      "The review",
      "People examine possibilities, limitations and sources before deciding what the evidence supports.",
      architectureImage,
    ],
  ];
  const evidence = [
    [
      "The original frame",
      "Start with what was recorded. Keep source media beside candidate observations so an analyst can return to the original context.",
      streetImage,
    ],
    [
      "A wider setting",
      "Examine the surrounding space. Geography provides context for a relationship, without proving that the relationship exists.",
      observationImage,
    ],
    [
      "A different moment",
      "Time changes what a scene can tell you. Keep the sequence visible and examine the gaps between observations.",
      nightImage,
    ],
  ];
  function select(buttons, data, image, title, copy) {
    let request = 0,
      transition;
    buttons.forEach((button, i) =>
      button.addEventListener("click", async () => {
        if (button.getAttribute("aria-pressed") === "true") return;
        const token = ++request;
        buttons.forEach((b) =>
          b.setAttribute("aria-pressed", String(b === button)),
        );
        const [heading, description, asset] = data[i];
        const preload = new Image();
        preload.src = asset;
        try {
          await preload.decode();
        } catch {}
        if (token !== request) return;
        const apply = () => {
          image.src = preload.src;
          image.removeAttribute("srcset");
          image.alt = `Illustrative ${heading.toLowerCase()} photograph`;
          title.textContent = heading;
          copy.textContent = description;
        };
        transition?.kill();
        gsap.killTweensOf([image, title, copy]);
        if (reduced.matches) {
          apply();
          return;
        }
        transition = gsap
          .timeline()
          .to([image, title, copy], { opacity: 0, duration: 0.2 })
          .call(apply)
          .fromTo(
            image,
            { scale: 1.06 },
            { scale: 1, duration: 0.85, ease: "power3.out" },
          )
          .to([image, title, copy], { opacity: 1, duration: 0.4 }, 0.22);
      }),
    );
  }
  const orbitButtons = [...document.querySelectorAll("[data-orbit]")];
  if (orbitButtons.length)
    select(
      orbitButtons,
      orbital,
      document.querySelector(".orbit-photo"),
      document.querySelector("#orbit-name"),
      document.querySelector("#orbit-copy"),
    );
  const evidenceButtons = [...document.querySelectorAll("[data-evidence]")];
  if (evidenceButtons.length)
    select(
      evidenceButtons,
      evidence,
      document.querySelector(".inspection-photo"),
      document.querySelector("#inspection-title"),
      document.querySelector("#inspection-copy"),
    );
  const zoom = document.querySelector(".inspect-zoom");
  zoom?.addEventListener("click", () => {
    const enlarged = zoom.getAttribute("aria-pressed") !== "true";
    zoom.setAttribute("aria-pressed", String(enlarged));
    zoom.setAttribute(
      "aria-label",
      enlarged ? "Restore evidence photograph" : "Enlarge evidence photograph",
    );
    zoom.textContent = enlarged ? "−" : "+";
    zoom.parentElement.classList.toggle("is-zoomed", enlarged);
  });
  const mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", () => {
    if (document.querySelector(".route-title"))
      gsap.from(".route-title", {
        y: 50,
        opacity: 0,
        duration: 1.25,
        ease: "power3.out",
        delay: 0.15,
      });
    document.querySelectorAll(".atlas-photos figure").forEach((el, i) =>
      gsap.to(el, {
        y: i === 1 ? -35 : 35,
        rotation: i === 1 ? -2 : 2,
        ease: "none",
        scrollTrigger: {
          trigger: ".platform-opening",
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      }),
    );
    document.querySelectorAll(".assembly-row").forEach((el) =>
      gsap.from(el, {
        y: 40,
        opacity: 0.25,
        scrollTrigger: {
          trigger: el,
          start: "top 92%",
          end: "top 60%",
          scrub: 0.7,
        },
      }),
    );
    if (document.querySelector(".orbit-ring"))
      gsap.to(".orbit-ring", {
        rotation: 50,
        ease: "none",
        scrollTrigger: {
          trigger: ".platform-orbit",
          start: "top bottom",
          end: "bottom top",
          scrub: 1,
        },
      });
    if (document.querySelector(".mission-landscape")) {
      gsap.to(".mission-landscape", {
        scale: 1.16,
        yPercent: 12,
        ease: "none",
        scrollTrigger: {
          trigger: ".mission-opening",
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      });
      const path = document.querySelector(".mission-contour path"),
        length = path.getTotalLength();
      gsap.fromTo(
        path,
        { strokeDasharray: length, strokeDashoffset: length },
        {
          strokeDashoffset: 0,
          duration: 2.6,
          ease: "power2.inOut",
          delay: 0.4,
        },
      );
      gsap.from(".journey-line i", {
        scaleY: 0,
        ease: "none",
        scrollTrigger: {
          trigger: ".mission-journey",
          start: "top 50%",
          end: "bottom 60%",
          scrub: 0.7,
        },
      });
      document.querySelectorAll(".journey-stop").forEach((el) =>
        gsap.from(el.querySelector(".stop-title"), {
          y: 50,
          opacity: 0.15,
          ease: "none",
          scrollTrigger: {
            trigger: el,
            start: "top 90%",
            end: "top 45%",
            scrub: 0.7,
          },
        }),
      );
      gsap.fromTo(
        ".planning-sheet",
        { rotation: 6, y: 60 },
        {
          rotation: -2,
          y: -25,
          ease: "none",
          scrollTrigger: {
            trigger: ".stop-plan",
            start: "top 80%",
            end: "bottom 20%",
            scrub: 1,
          },
        },
      );
      gsap.fromTo(
        ".flight-panorama img",
        { scale: 1.2 },
        {
          scale: 1,
          ease: "none",
          scrollTrigger: {
            trigger: ".flight-panorama",
            start: "top bottom",
            end: "bottom top",
            scrub: 1,
          },
        },
      );
    }
    if (document.querySelector(".archive-fan")) {
      document.querySelectorAll(".archive-fan figure").forEach((el, i) =>
        gsap.from(el, {
          rotation: 0,
          x: (1 - i) * 85,
          y: 40,
          opacity: 0,
          duration: 1.4,
          delay: 0.2 + i * 0.12,
          ease: "power3.out",
        }),
      );
      gsap.to(".archive-fan", {
        y: -40,
        rotation: -3,
        ease: "none",
        scrollTrigger: {
          trigger: ".archive-opening",
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      });
      document.querySelectorAll(".reasoning-track article").forEach((el, i) =>
        gsap.from(el, {
          y: 40,
          opacity: 0.2,
          scrollTrigger: {
            trigger: el,
            start: `top ${90 - i * 8}%`,
            end: `top ${65 - i * 8}%`,
            scrub: 1,
          },
        }),
      );
      gsap.from(".intelligence-close h2", {
        y: 70,
        opacity: 0.3,
        ease: "none",
        scrollTrigger: {
          trigger: ".intelligence-close",
          start: "top 70%",
          end: "top 10%",
          scrub: 1,
        },
      });
    }
  });
}
