import { PageFlip } from "page-flip";

// Eight real HTML leaves. Soft page geometry is clipped around the dragged corner,
// including the reverse surface and the library's dynamic inner/outer shadows.
export function initBook({ gsap, ScrollTrigger, reduced }) {
  const stage = document.querySelector(".book-stage");
  if (!stage) return;
  const shell = stage.querySelector(".book-shell");
  const host = stage.querySelector(".book-pages");
  const tabs = [...stage.querySelectorAll("[data-chapter]")];
  const prev = stage.querySelector("#book-prev");
  const next = stage.querySelector("#book-next");
  const status = stage.querySelector(".book-status");
  const pages = [];
  [...host.querySelectorAll(".book-spread")].forEach((spread, chapter) => {
    [...spread.children].forEach((content) => {
      const leaf = document.createElement("div");
      leaf.className = `paper-leaf spread-${chapter}`;
      leaf.dataset.density = "soft";
      leaf.setAttribute("role", "group");
      leaf.setAttribute(
        "aria-label",
        `Chapter ${chapter + 1}, page ${pages.length + 1}`,
      );
      leaf.append(content);
      pages.push(leaf);
    });
  });
  host.replaceChildren(...pages);
  host.querySelectorAll("img").forEach((img) => (img.loading = "eager"));
  stage.querySelector(".turning-leaf")?.remove();
  tabs.forEach((tab) => {
    tab.removeAttribute("aria-controls");
    tab.removeAttribute("role");
    tab.setAttribute("aria-pressed", "false");
    tab.removeAttribute("aria-selected");
    tab.tabIndex = 0;
  });
  stage.querySelector(".chapter-tabs").setAttribute("role", "group");
  shell.classList.add("physical-book");
  const book = new PageFlip(host, {
    width: Math.round(
      innerWidth <= 720 ? shell.clientWidth : shell.clientWidth / 2,
    ),
    height: shell.clientHeight,
    size: "stretch",
    minWidth: 280,
    maxWidth: 700,
    minHeight: 340,
    maxHeight: 650,
    usePortrait: true,
    showCover: false,
    drawShadow: true,
    maxShadowOpacity: 0.38,
    flippingTime: 1250,
    autoSize: false,
    mobileScrollSupport: false,
    swipeDistance: 35,
    clickEventForward: true,
    disableFlipByClick: true,
    showPageCorners: !reduced.matches,
    startZIndex: 2,
  });
  let current = 0,
    desired = 0,
    busy = false,
    dragging = false;
  const portrait = () => book.getOrientation() === "portrait";
  function sync(index) {
    current = index;
    const chapter = Math.floor(index / 2);
    tabs.forEach((tab, i) =>
      tab.setAttribute("aria-pressed", String(i === chapter)),
    );
    prev.setAttribute(
      "aria-label",
      portrait() ? "Previous page" : "Previous chapter",
    );
    next.setAttribute("aria-label", portrait() ? "Next page" : "Next chapter");
    prev.disabled = index === 0;
    next.disabled = index >= (portrait() ? 7 : 6);
    status.textContent = `Chapter ${chapter + 1} of 4 · ${portrait() ? `Page ${index + 1} of 8` : "Drag a corner to turn the page"}`;
    pages.forEach((page, i) => {
      const visible = i === index || (!portrait() && i === index + 1);
      page.inert = !visible;
      page.setAttribute("aria-hidden", String(!visible));
    });
  }
  function navigate(index) {
    shell.scrollIntoView({
      block: "center",
      behavior: reduced.matches ? "instant" : "smooth",
    });
    dragging = false;
    desired = Math.max(0, Math.min(portrait() ? 7 : 6, index));
    if (!portrait()) desired = Math.floor(desired / 2) * 2;
    if (busy || desired === current) return;
    if (reduced.matches) book.turnToPage(desired);
    else book.flip(desired, desired > current ? "bottom" : "top");
  }
  book.on("flip", (e) => {
    if (dragging) desired = e.data;
    sync(e.data);
  });
  book.on("changeState", (e) => {
    busy = e.data !== "read";
    shell.classList.toggle("is-turning", busy);
    if (busy) pages.forEach((page) => (page.inert = true));
    else {
      sync(book.getCurrentPageIndex());
      if (desired !== current) navigate(desired);
    }
  });
  // A direct drag sets the intended destination; only button requests are queued.
  host.addEventListener("pointerdown", () => {
    dragging = true;
    desired = current;
  });
  book.on("changeOrientation", () => {
    sync(book.getCurrentPageIndex());
    ScrollTrigger.refresh();
  });
  book.loadFromHTML(pages);
  sync(0);
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => navigate(i * 2));
    tab.addEventListener("keydown", (e) => {
      let target;
      if (e.key === "ArrowRight") target = Math.min(3, i + 1);
      if (e.key === "ArrowLeft") target = Math.max(0, i - 1);
      if (e.key === "Home") target = 0;
      if (e.key === "End") target = 3;
      if (target !== undefined) {
        e.preventDefault();
        tabs[target].focus();
        navigate(target * 2);
      }
    });
  });
  prev.addEventListener("click", () =>
    navigate(desired - (portrait() ? 1 : 2)),
  );
  next.addEventListener("click", () =>
    navigate(desired + (portrait() ? 1 : 2)),
  );
  reduced.addEventListener("change", () => {
    if (reduced.matches) book.turnToPage(desired);
  });
}

export function initStoryMotion({ gsap, ScrollTrigger }) {
  const stage = document.querySelector(".drone-stage");
  if (!stage) return;
  const home = document.querySelector(".hero");
  const mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", () => {
    // Move, never clone: this is the only drone image in the entire home document.
    document.body.append(stage);
    stage.classList.add("persistent-drone");
    const image = stage.querySelector("img");
    gsap.set(image, { clearProps: "all" });
    let stops = [],
      targetY = scrollY,
      state,
      pointerX = 0,
      pointerY = 0;
    const clamp = gsap.utils.clamp;
    const pose = (selector, offset, x, y, w, r) => {
      const el = document.querySelector(selector);
      return {
        at: el.getBoundingClientRect().top + scrollY + el.offsetHeight * offset,
        x,
        y,
        w,
        r,
      };
    };
    function measure() {
      const mobile = innerWidth <= 720;
      stops = [
        pose(
          ".hero",
          0,
          mobile ? 0.44 : 0.4,
          mobile ? 0.46 : 0.44,
          mobile ? 1.15 : 0.77,
          -6,
        ),
        pose(".world", 0, 0.77, 0.24, mobile ? 0.48 : 0.29, 9),
        pose(".world", 0.65, 0.8, 0.29, mobile ? 0.41 : 0.23, -4),
        pose(".capture", 0, 0.74, 0.23, mobile ? 0.38 : 0.23, -9),
        pose(".capture", 0.65, 0.82, 0.22, mobile ? 0.3 : 0.16, 5),
        pose(".flight-passage", 0.12, 0.51, 0.43, mobile ? 1.0 : 0.67, -8),
        pose(".flight-passage", 0.62, 0.72, 0.36, mobile ? 0.63 : 0.4, 7),
        pose(".observation-book", 0, 0.88, 0.21, mobile ? 0.3 : 0.16, -4),
        pose(".observation-book", 0.7, 0.9, 0.21, mobile ? 0.28 : 0.14, -6),
        pose(".judgment-layout", 0, 0.88, 0.23, mobile ? 0.27 : 0.15, 3),
        pose(".system-editorial", 0, 0.86, 0.23, mobile ? 0.28 : 0.16, -5),
        pose(".reprise", 0.05, 0.64, 0.28, mobile ? 0.74 : 0.53, -6),
        pose(".footer", 0, 0.87, 0.22, mobile ? 0.3 : 0.17, 3),
        pose(".footer", 0.9, 0.88, 0.72, mobile ? 0.25 : 0.14, -7),
      ].sort((a, b) => a.at - b.at);
      targetY = scrollY;
      state = { ...sample(targetY) };
    }
    function sample(y) {
      let a = stops[0],
        b = a;
      for (let i = 1; i < stops.length; i++) {
        b = stops[i];
        if (y <= b.at) break;
        a = b;
      }
      let t = clamp(0, 1, (y - a.at) / Math.max(1, b.at - a.at));
      t = t * t * (3 - 2 * t);
      return Object.fromEntries(
        ["x", "y", "w", "r"].map((k) => [k, a[k] + (b[k] - a[k]) * t]),
      );
    }
    measure();
    const setX = gsap.quickSetter(stage, "x", "px"),
      setY = gsap.quickSetter(stage, "y", "px"),
      setR = gsap.quickSetter(stage, "rotation", "deg");
    gsap.set(stage, { xPercent: -50, yPercent: -50 });
    const tick = (_, delta) => {
      const target = sample(targetY),
        blend = 1 - Math.exp(-delta / 140);
      for (const k of ["x", "y", "w", "r"])
        state[k] += (target[k] - state[k]) * blend;
      const time = performance.now() / 1000;
      setX(state.x * innerWidth + pointerX);
      setY(state.y * innerHeight + Math.sin(time * 1.8) * 4 + pointerY);
      setR(state.r + Math.sin(time * 0.8) * 0.7);
      stage.style.width = `${state.w * innerWidth}px`;
    };
    gsap.ticker.add(tick);
    const trigger = ScrollTrigger.create({
      start: 0,
      end: "max",
      onUpdate: (self) => (targetY = self.scroll()),
      onRefresh: measure,
    });
    const move = (e) => {
      if (e.pointerType === "mouse" && scrollY < home.offsetHeight * 0.7) {
        pointerX = (e.clientX / innerWidth - 0.5) * 16;
        pointerY = (e.clientY / innerHeight - 0.5) * 10;
      }
    };
    const leave = () => (pointerX = pointerY = 0);
    home.addEventListener("pointermove", move);
    home.addEventListener("pointerleave", leave);
    const route = document.querySelector(".flight-route path");
    const length = route.getTotalLength();
    gsap.fromTo(
      route,
      { strokeDasharray: length, strokeDashoffset: length },
      {
        strokeDashoffset: 0,
        ease: "none",
        scrollTrigger: {
          trigger: ".flight-passage",
          start: "top 80%",
          end: "bottom 40%",
          scrub: 1,
        },
      },
    );
    gsap.fromTo(
      ".flight-words span:first-child",
      { xPercent: -8 },
      {
        xPercent: 4,
        ease: "none",
        scrollTrigger: {
          trigger: ".flight-passage",
          start: "top bottom",
          end: "bottom top",
          scrub: 1,
        },
      },
    );
    gsap.fromTo(
      ".flight-words span:last-child",
      { xPercent: 8 },
      {
        xPercent: -4,
        ease: "none",
        scrollTrigger: {
          trigger: ".flight-passage",
          start: "top bottom",
          end: "bottom top",
          scrub: 1,
        },
      },
    );
    return () => {
      trigger.kill();
      gsap.ticker.remove(tick);
      home.removeEventListener("pointermove", move);
      home.removeEventListener("pointerleave", leave);
      stage.classList.remove("persistent-drone");
      gsap.set(stage, { clearProps: "all" });
      home.append(stage);
    };
  });
}
