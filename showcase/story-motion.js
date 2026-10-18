// A four chapter book. Page folds use only 2D transforms and the existing image assets.
export function initBook({ gsap, ScrollTrigger, reduced, getLenis }) {
  const stage = document.querySelector(".book-stage");
  if (!stage) return;
  const shell = stage.querySelector(".book-shell");
  const spreads = [...stage.querySelectorAll(".book-spread")];
  const tabs = [...stage.querySelectorAll("[data-chapter]")];
  const leaf = stage.querySelector(".turning-leaf");
  const prev = stage.querySelector("#book-prev");
  const next = stage.querySelector("#book-next");
  const status = stage.querySelector(".book-status");
  const mm = gsap.matchMedia();
  let active = 0;
  let desired = 0;
  let turning = false;
  let turn;
  let pin;

  function expose(index) {
    spreads.forEach((spread, i) => {
      spread.hidden = i !== index;
      spread.inert = i !== index;
    });
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
    });
    prev.disabled = index === 0;
    next.disabled = index === spreads.length - 1;
    status.textContent = `Chapter ${index + 1} of ${spreads.length}`;
    active = index;
  }

  function request(index) {
    desired = Math.max(0, Math.min(spreads.length - 1, index));
    if (turning || desired === active) return;
    if (reduced.matches) {
      expose(desired);
      return;
    }
    const target = desired;
    const direction = target > active ? 1 : -1;
    const previous = spreads[active];
    const incoming = spreads[target];
    const oldArt = previous.querySelector(".page-right");
    const newArt = incoming.querySelector(".page-right");
    turning = true;
    leaf.innerHTML = oldArt.innerHTML;
    leaf.className = `turning-leaf spread-${active}`;
    gsap.set(leaf, { visibility: "visible", scaleX: 1, skewY: 0, opacity: 1 });
    turn = gsap.timeline({
      onComplete: () => {
        gsap.set(leaf, {
          visibility: "hidden",
          clearProps: "transform,opacity",
        });
        leaf.replaceChildren();
        turning = false;
        request(desired);
      },
    });
    turn
      .to(
        previous.querySelector(".page-copy"),
        { y: -12 * direction, opacity: 0, duration: 0.22, ease: "power2.in" },
        0,
      )
      .to(
        leaf,
        { scaleX: 0, skewY: direction * 8, duration: 0.44, ease: "power2.in" },
        0,
      )
      .call(
        () => {
          expose(target);
          gsap.set(previous.querySelector(".page-copy"), {
            clearProps: "transform,opacity",
          });
          leaf.innerHTML = newArt.innerHTML;
          leaf.className = `turning-leaf spread-${target}`;
          gsap.set(newArt, { opacity: 0 });
          gsap.set(leaf, { scaleX: 0, skewY: -direction * 8 });
        },
        null,
        0.44,
      )
      .to(
        leaf,
        { scaleX: 1, skewY: 0, duration: 0.52, ease: "power3.out" },
        0.44,
      )
      .fromTo(
        incoming.querySelector(".page-copy"),
        { y: 18 * direction, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.52, ease: "power3.out" },
        0.44,
      )
      .set(newArt, { clearProps: "opacity" }, 0.96);
  }

  function navigate(index) {
    index = Math.max(0, Math.min(spreads.length - 1, index));
    if (pin && !reduced.matches) {
      const y = pin.start + (index / 3) * (pin.end - pin.start);
      const lenis = getLenis();
      if (lenis) lenis.scrollTo(y, { duration: 0.85 });
      else scrollTo({ top: y, behavior: "smooth" });
    } else {
      shell.scrollIntoView({
        block: "start",
        behavior: reduced.matches ? "instant" : "smooth",
      });
    }
    request(index);
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => navigate(i));
    tab.addEventListener("keydown", (e) => {
      let target;
      if (e.key === "ArrowRight") target = Math.min(3, i + 1);
      if (e.key === "ArrowLeft") target = Math.max(0, i - 1);
      if (e.key === "Home") target = 0;
      if (e.key === "End") target = 3;
      if (target !== undefined) {
        e.preventDefault();
        tabs[target].focus({ preventScroll: true });
        navigate(target);
      }
    });
  });
  prev.addEventListener("click", () => navigate(desired - 1));
  next.addEventListener("click", () => navigate(desired + 1));
  let pointer;
  shell.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse") pointer = { x: e.clientX, y: e.clientY };
  });
  shell.addEventListener("pointerup", (e) => {
    if (!pointer) return;
    const dx = e.clientX - pointer.x,
      dy = e.clientY - pointer.y;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.8)
      navigate(desired + (dx < 0 ? 1 : -1));
    pointer = undefined;
  });
  shell.addEventListener("pointercancel", () => {
    pointer = undefined;
  });
  mm.add(
    "(min-width: 900px) and (min-height: 720px) and (prefers-reduced-motion: no-preference)",
    () => {
      pin = ScrollTrigger.create({
        trigger: stage,
        pin: true,
        start: "top top",
        end: () => `+=${Math.max(1800, innerHeight * 2.6)}`,
        anticipatePin: 1,
        invalidateOnRefresh: true,
        onUpdate: (self) => request(Math.min(3, Math.round(self.progress * 3))),
      });
      return () => {
        pin = undefined;
      };
    },
  );
  reduced.addEventListener("change", () => {
    turn?.kill();
    turning = false;
    gsap.set(leaf, { visibility: "hidden" });
    spreads.forEach((s) =>
      gsap.set(s.querySelectorAll(".page-copy,.page-right"), {
        clearProps: "transform,opacity",
      }),
    );
    expose(desired);
  });
}

export function initStoryMotion({ gsap, ScrollTrigger, reduced }) {
  if (!document.querySelector(".hero")) return;
  const mm = gsap.matchMedia();
  mm.add(
    {
      desktop: "(min-width:721px)",
      motion: "(prefers-reduced-motion:no-preference)",
    },
    (ctx) => {
      if (!ctx.conditions.motion) return;
      const idle = gsap.to(".hero-drone", {
        y: -9,
        rotation: -3.5,
        duration: 2.8,
        ease: "sine.inOut",
        yoyo: true,
        repeat: -1,
        delay: 1.8,
        paused: true,
      });
      ScrollTrigger.create({
        trigger: ".hero",
        start: "top bottom",
        end: "bottom top",
        onToggle: (self) => (self.isActive ? idle.play() : idle.pause()),
      });
      const hover = document.querySelector(".drone-hover");
      const hero = document.querySelector(".hero");
      const moveX = gsap.quickTo(hover, "x", {
        duration: 1,
        ease: "power3.out",
      });
      const moveY = gsap.quickTo(hover, "y", {
        duration: 1,
        ease: "power3.out",
      });
      const move = (e) => {
        if (e.pointerType === "mouse") {
          const r = hero.getBoundingClientRect();
          moveX((e.clientX / r.width - 0.5) * 28);
          moveY(((e.clientY - r.top) / r.height - 0.5) * 20);
        }
      };
      const leave = () => {
        moveX(0);
        moveY(0);
      };
      hero.addEventListener("pointermove", move);
      hero.addEventListener("pointerleave", leave);
      gsap.fromTo(
        ".world-flyby",
        { xPercent: -60, yPercent: 20, scale: 0.68 },
        {
          xPercent: 170,
          yPercent: -55,
          scale: 0.42,
          ease: "none",
          scrollTrigger: {
            trigger: ".world",
            start: "top bottom",
            end: "bottom top",
            scrub: 1.4,
          },
        },
      );
      gsap.fromTo(
        ".capture-drone",
        { xPercent: -18, yPercent: 25, scale: 0.8 },
        {
          xPercent: 55,
          yPercent: -15,
          scale: 0.18,
          autoAlpha: 0,
          ease: "power2.inOut",
          scrollTrigger: {
            trigger: ".capture",
            start: "top 75%",
            end: "top -20%",
            scrub: 1,
          },
        },
      );
      const route = document.querySelector(".flight-route path");
      const length = route.getTotalLength();
      gsap.set(route, { strokeDasharray: length, strokeDashoffset: length });
      gsap.to(route, {
        strokeDashoffset: 0,
        ease: "none",
        scrollTrigger: {
          trigger: ".flight-passage",
          start: "top 75%",
          end: "bottom 35%",
          scrub: 1,
        },
      });
      gsap.fromTo(
        ".passage-drone",
        {
          xPercent: ctx.conditions.desktop ? -32 : -10,
          yPercent: 35,
          rotation: -10,
          scale: 0.88,
        },
        {
          xPercent: ctx.conditions.desktop ? 54 : 13,
          yPercent: -20,
          rotation: 6,
          scale: 1.05,
          ease: "none",
          scrollTrigger: {
            trigger: ".flight-passage",
            start: "top bottom",
            end: "bottom top",
            scrub: 1.2,
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
      gsap.fromTo(
        ".reprise-drone",
        { xPercent: 35, yPercent: 22, rotation: 7, scale: 0.82 },
        {
          xPercent: -4,
          yPercent: -10,
          rotation: -5,
          scale: 1,
          ease: "none",
          scrollTrigger: {
            trigger: ".reprise",
            start: "top bottom",
            end: "bottom top",
            scrub: 1.2,
          },
        },
      );
      const statement = document.querySelector(".judgment-copy>p");
      if (!statement.querySelector("span"))
        statement.innerHTML = statement.innerHTML
          .split(/<br\s*\/?>/)
          .map((line) => `<span>${line.trim()}</span>`)
          .join("");
      gsap.fromTo(
        statement.children,
        { opacity: 0.18, y: 12 },
        {
          opacity: 1,
          y: 0,
          stagger: 0.25,
          ease: "none",
          scrollTrigger: {
            trigger: statement,
            start: "top 85%",
            end: "bottom 45%",
            scrub: 0.8,
          },
        },
      );
      const wordmark = document.querySelector(".footer-wordmark");
      if (!wordmark.querySelector("span")) {
        const span = document.createElement("span");
        span.textContent = wordmark.textContent;
        wordmark.replaceChildren(span);
      }
      gsap.fromTo(
        wordmark.firstElementChild,
        { yPercent: 90 },
        {
          yPercent: 0,
          ease: "power2.out",
          scrollTrigger: {
            trigger: wordmark,
            start: "top 98%",
            end: "bottom 92%",
            scrub: 1,
          },
        },
      );
      return () => {
        hero.removeEventListener("pointermove", move);
        hero.removeEventListener("pointerleave", leave);
      };
    },
  );
}
