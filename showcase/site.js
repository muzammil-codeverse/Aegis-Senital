import { initBook, initStoryMotion } from "./story-motion.js";
import {
  initEditorialMotion,
  initSceneTransitions,
} from "./editorial-motion.js";
import "./cinematic.css";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import "lenis/dist/lenis.css";

gsap.registerPlugin(ScrollTrigger);
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const menu = document.querySelector("#site-menu");
const menuButton = document.querySelector("#menu-button");
const header = document.querySelector(".header");
let lenis;
const media = gsap.matchMedia();
const sections = [...document.querySelectorAll(".light-scene, .dark-scene")];
document
  .querySelectorAll(".header-links a, .menu-layout nav a")
  .forEach((a) => {
    if (new URL(a.href).pathname === location.pathname)
      a.setAttribute("aria-current", "page");
  });
let framePending = false;
function updateHeader() {
  const active = sections.findLast((s) => s.getBoundingClientRect().top <= 90);
  header?.classList.toggle(
    "on-dark",
    active?.classList.contains("dark-scene") ?? false,
  );
  header?.classList.toggle("scrolled", scrollY > 70);
}
function scheduleHeader() {
  if (framePending) return;
  framePending = true;
  requestAnimationFrame(() => {
    updateHeader();
    framePending = false;
  });
}
addEventListener("scroll", scheduleHeader, { passive: true });
addEventListener("resize", scheduleHeader, { passive: true });
updateHeader();

function openMenu() {
  menu.showModal();
  menuButton.setAttribute("aria-expanded", "true");
  lenis?.stop();
  if (!reduced.matches) {
    gsap.fromTo(
      menu.querySelectorAll(".menu-layout nav a"),
      { y: 35, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.55, stagger: 0.06, ease: "power3.out" },
    );
  }
}
function closeMenu() {
  menu.close();
  menuButton.setAttribute("aria-expanded", "false");
  lenis?.start();
  menuButton.focus({ preventScroll: true });
}
menuButton?.addEventListener("click", openMenu);
document.querySelector("#menu-close")?.addEventListener("click", closeMenu);
menu?.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeMenu();
});
menu?.addEventListener("close", () => {
  menuButton?.setAttribute("aria-expanded", "false");
  lenis?.start();
});

// Keep smooth scrolling and scene choreography on one animation clock.
media.add(
  {
    desktop: "(min-width: 721px)",
    motion: "(prefers-reduced-motion: no-preference)",
  },
  (ctx) => {
    if (!ctx.conditions.motion) return;
    const desktop = ctx.conditions.desktop;
    let ticker;
    if (desktop && matchMedia("(pointer:fine)").matches) {
      lenis = new Lenis({
        lerp: 0.09,
        smoothWheel: true,
        autoRaf: false,
        anchors: false,
      });
      lenis.on("scroll", ScrollTrigger.update);
      ticker = (time) => lenis.raf(time * 1000);
      gsap.ticker.add(ticker);
      gsap.ticker.lagSmoothing(0);
    }
    const hero = document.querySelector(".hero");
    if (hero) {
      gsap.fromTo(
        ".hero h1 span",
        { yPercent: 35, opacity: 0 },
        {
          yPercent: 0,
          opacity: 1,
          duration: 1.15,
          stagger: 0.09,
          ease: "power3.out",
        },
      );
      gsap.to(".hero-type", {
        yPercent: -13,
        ease: "none",
        scrollTrigger: {
          trigger: hero,
          start: "top top",
          end: "bottom top",
          scrub: 1,
        },
      });
    }
    document.querySelectorAll(".parallax-image").forEach((img) =>
      gsap.fromTo(
        img,
        { yPercent: -7 },
        {
          yPercent: 4,
          ease: "none",
          scrollTrigger: {
            trigger: img.parentElement,
            start: "top bottom",
            end: "bottom top",
            scrub: 1,
          },
        },
      ),
    );
    document.querySelectorAll(".parallax-detail").forEach((img) =>
      gsap.fromTo(
        img,
        { yPercent: -10 },
        {
          yPercent: 0,
          ease: "none",
          scrollTrigger: {
            trigger: img.closest("figure"),
            start: "top bottom",
            end: "bottom top",
            scrub: 1,
          },
        },
      ),
    );
    if (document.querySelector(".capture")) {
      const capture = gsap.timeline({
        scrollTrigger: {
          trigger: ".capture",
          start: "top top",
          end: "bottom bottom",
          scrub: 1,
        },
      });
      capture
        .to(".capture-image", {
          clipPath: "circle(110% at 65% 38%)",
          duration: 0.7,
          ease: "power2.inOut",
        })
        .to(".capture-image img", { scale: 1.12, duration: 1, ease: "none" }, 0)
        .fromTo(
          ".frame-corners",
          { opacity: 0, scale: 0.85 },
          { opacity: 1, scale: 1.05, duration: 0.5 },
          0.25,
        )
        .fromTo(".capture-copy", { y: 60 }, { y: 0, duration: 0.7 }, 0.25);
    }
    gsap.utils.toArray(".reveal").forEach((el) =>
      gsap.fromTo(
        el,
        { y: 45, opacity: 0.25 },
        {
          y: 0,
          opacity: 1,
          duration: 0.9,
          ease: "power2.out",
          scrollTrigger: {
            trigger: el,
            start: "top 90%",
            end: "top 55%",
            scrub: 0.6,
          },
        },
      ),
    );
    if (document.querySelector(".evidence"))
      gsap.fromTo(
        ".evidence",
        { y: 60, rotation: -7 },
        {
          y: 0,
          rotation: -2,
          ease: "none",
          scrollTrigger: {
            trigger: ".judgment-layout",
            start: "top bottom",
            end: "top 25%",
            scrub: 1,
          },
        },
      );
    if (document.querySelector(".system-images"))
      gsap.fromTo(
        ".system-images figure:last-child",
        { y: 50 },
        {
          y: -25,
          ease: "none",
          scrollTrigger: {
            trigger: ".system-images",
            start: "top bottom",
            end: "bottom top",
            scrub: 1,
          },
        },
      );
    return () => {
      if (ticker) gsap.ticker.remove(ticker);
      lenis?.destroy();
      lenis = undefined;
    };
  },
);

function goTo(el) {
  if (lenis) lenis.scrollTo(el, { duration: 1.1, offset: -75 });
  else el.scrollIntoView({ behavior: reduced.matches ? "instant" : "smooth" });
}
document.querySelectorAll('a[href^="#"]').forEach((a) =>
  a.addEventListener("click", (e) => {
    const target = document.querySelector(a.getAttribute("href"));
    if (target) {
      e.preventDefault();
      goTo(target);
      if (a.classList.contains("skip")) {
        target.tabIndex = -1;
        target.focus({ preventScroll: true });
      }
    }
  }),
);
document.querySelector(".back-top")?.addEventListener("click", () => {
  if (lenis) lenis.scrollTo(0, { duration: 1.2 });
  else scrollTo({ top: 0, behavior: reduced.matches ? "instant" : "smooth" });
});

const evidenceDialog = document.querySelector("#evidence-dialog");
const evidenceButton = document.querySelector(".evidence");
evidenceButton?.addEventListener("click", () => {
  evidenceDialog.showModal();
  lenis?.stop();
  if (!reduced.matches)
    gsap.fromTo(
      ".inspection-image",
      { clipPath: "inset(10% 20%)", opacity: 0.5 },
      {
        clipPath: "circle(110% at 65% 38%)",
        opacity: 1,
        duration: 0.6,
        ease: "power3.out",
      },
    );
});
function closeEvidence() {
  evidenceDialog.close();
  lenis?.start();
  evidenceButton.focus({ preventScroll: true });
}
evidenceDialog
  ?.querySelector(".dialog-close")
  .addEventListener("click", closeEvidence);
evidenceDialog?.addEventListener("cancel", (e) => {
  e.preventDefault();
  closeEvidence();
});
evidenceDialog?.addEventListener("click", (e) => {
  if (e.target === evidenceDialog) {
    const r = evidenceDialog.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      closeEvidence();
  }
});

// No credential handling: the public build has no account service.
document
  .querySelector(".auth-form")
  ?.addEventListener("submit", (e) => e.preventDefault());

initSceneTransitions({ gsap, reduced, getLenis: () => lenis });
Promise.all(
  [...document.images].map((img) =>
    img.complete
      ? Promise.resolve()
      : new Promise((resolve) => {
          img.addEventListener("load", resolve, { once: true });
          img.addEventListener("error", resolve, { once: true });
        }),
  ),
).then(() => ScrollTrigger.refresh());
document.fonts.ready.then(() => ScrollTrigger.refresh());

initBook({ gsap, ScrollTrigger, reduced, getLenis: () => lenis });
initStoryMotion({ gsap, ScrollTrigger, reduced });

initEditorialMotion({ gsap, ScrollTrigger, reduced });
