import "./style.css";
import { mountDemo } from "./demo";

const reducesMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function $<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Missing ${selector}`);
  return element;
}

const clamp = (value: number, low = 0, high = 1) => Math.min(Math.max(value, low), high);
/** Progress of `value` through the range from `start` to `end`, clamped to 0...1. */
const span = (value: number, start: number, end: number) => clamp((value - start) / (end - start));
const smooth = (t: number) => t * t * (3 - 2 * t);
const mix = (a: number, b: number, t: number) => a + (b - a) * t;

// MARK: The closing lid

const scene = $<HTMLElement>(".scene");
const stage = $<HTMLElement>(".stage");
const headline = $<HTMLElement>("h1");
const heroCopy = $<HTMLElement>(".hero-copy");
const under = $<HTMLElement>(".under");
const laptop = $<HTMLElement>(".laptop");
const lid = $<HTMLElement>(".lid");
const ember = $<HTMLElement>(".ember");
const halo = $<HTMLElement>(".halo");
const dusk = $<HTMLElement>(".dusk");
const night = $<HTMLElement>(".night");
const nightCopy = $<HTMLElement>(".night-copy");
const nav = $<HTMLElement>(".nav");
const dawn = $<HTMLElement>(".dawn");
const railFill = $<HTMLElement>(".rail-fill");
const rail = $<HTMLElement>(".rail");

const INK = [33, 32, 28];
const PAPER = [245, 242, 238];

let geometry = { angle: 18, openX: 0, openY: 0, closedX: 0, closedY: 0, closedScale: 0.1, size: 0 };

/** Fits the lid to the words: the open angle is whatever clears the bottom-right corner of the headline. */
function measure() {
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  const gutter = clamp(width * 0.028, 16, 40);
  const line = clamp(width * 0.015, 10, 24);
  const baseY = height - under.offsetHeight - clamp(height * 0.034, 20, 36) - line - 18;
  const span_ = width - 2 * gutter;

  const words = headline.getBoundingClientRect();
  const stageTop = stage.getBoundingClientRect().top;
  const clearance = line + 22;
  const rise = baseY - (words.bottom - stageTop + clearance);
  const run = words.right - gutter;
  const angle = clamp((Math.atan2(rise, run) * 180) / Math.PI, 11, 40);

  // The ember keeps the logo's proportions: past the end of the lid, resting just above the base.
  const lidReach = span_ * 0.8;
  const size = Math.min(Math.max(span_ * 0.2, 104), height * 0.3);
  const radius = size / 2;
  const openX = gutter + span_ - size - span_ * 0.01;
  const openY = baseY - size - line * 0.9;
  const closedRadius = line * 0.95;
  const closedCenterX = gutter + lidReach + line * 2.5;
  const closedCenterY = baseY - line * 1.1 - 3;

  document.documentElement.style.setProperty("--base-y", `${baseY}px`);
  ember.style.setProperty("--ember-size", `${size}px`);
  geometry = {
    angle,
    openX,
    openY,
    closedX: closedCenterX - radius,
    closedY: closedCenterY - radius,
    closedScale: closedRadius / radius,
    size,
  };
}

function render(progress: number) {
  const closing = smooth(span(progress, 0.06, 0.62));
  // Paper to night directly passes through grey. Going through a sunset keeps the light warm all the way down.
  const sunset = smooth(span(progress, 0.14, 0.4));
  const dark = smooth(span(progress, 0.34, 0.62));
  const inverted = smooth(span(progress, 0.34, 0.54));
  const copyOut = span(progress, 0.02, 0.16);
  const copyIn = smooth(span(progress, 0.6, 0.76));
  const { angle, openX, openY, closedX, closedY, closedScale, size } = geometry;

  lid.style.transform = `rotate(${mix(-angle, 0, closing)}deg)`;

  const x = mix(openX, closedX, closing);
  const y = mix(openY, closedY, closing);
  ember.style.transform = `translate(${x}px, ${y}px) scale(${mix(1, closedScale, closing)})`;
  halo.style.transform = `translate(${x + size / 2}px, ${y + size / 2}px)`;
  halo.style.opacity = String(dark);

  const color = INK.map((channel, index) => Math.round(mix(channel, PAPER[index], inverted)));
  laptop.style.color = `rgb(${color.join(" ")})`;

  dusk.style.opacity = String(sunset);
  night.style.opacity = String(dark);
  nightCopy.style.opacity = String(copyIn);
  nightCopy.style.transform = `translateY(${mix(14, 0, copyIn)}px)`;

  heroCopy.style.opacity = String(1 - copyOut);
  heroCopy.style.transform = `translateY(${mix(0, -18, copyOut)}px)`;
  under.style.opacity = String(1 - copyOut);
  under.style.visibility = copyOut >= 1 ? "hidden" : "visible";
}

// MARK: Scroll

const toneSections = [...document.querySelectorAll<HTMLElement>("[data-tone]:not(.nav)")];
let frame = 0;

function onFrame() {
  frame = 0;
  const viewport = innerHeight;

  if (!reducesMotion) {
    const box = scene.getBoundingClientRect();
    const progress = clamp(-box.top / Math.max(box.height - viewport, 1));
    if (box.bottom > 0) render(progress);
    scene.dataset.tone = progress > 0.36 ? "night" : "day";

    const railBox = rail.getBoundingClientRect();
    railFill.style.transform = `scaleY(${clamp((viewport * 0.72 - railBox.top) / railBox.height)})`;
  }

  // The nav takes its colour from whatever is under it.
  const under_ = toneSections.find((section) => {
    const box = section.getBoundingClientRect();
    return box.top <= 40 && box.bottom > 40;
  });
  let tone = under_?.dataset.tone ?? "day";
  const box = under_?.getBoundingClientRect();
  // The dawn ends on paper, and with reduced motion the scene ends on night, so these change tone part way down.
  if (under_ === dawn && box) tone = 40 - box.top > box.height * 0.72 ? "day" : "night";
  if (reducesMotion && under_ === scene) tone = stage.getBoundingClientRect().bottom <= 40 ? "night" : "day";
  nav.dataset.tone = tone;
  // These two carry their own sky, and any band of colour would show against it.
  nav.dataset.clear = String(under_ === scene || under_ === dawn);
}

function requestFrame() {
  if (!frame) frame = requestAnimationFrame(onFrame);
}

addEventListener("scroll", requestFrame, { passive: true });
addEventListener("resize", () => {
  measure();
  requestFrame();
});

measure();
if (reducesMotion) {
  // Plain flow: the open laptop by day, then the night section below it.
  lid.style.transform = `rotate(${-geometry.angle}deg)`;
  ember.style.transform = `translate(${geometry.openX}px, ${geometry.openY}px)`;
}
onFrame();
// Web fonts change the headline's size, and with it the angle that clears it.
document.fonts?.ready.then(() => {
  measure();
  if (reducesMotion) {
    lid.style.transform = `rotate(${-geometry.angle}deg)`;
    ember.style.transform = `translate(${geometry.openX}px, ${geometry.openY}px)`;
  } else {
    onFrame();
  }
});

// MARK: Copy buttons

const copyStatus = $<HTMLElement>("#copy-status");

for (const button of document.querySelectorAll<HTMLButtonElement>("[data-copy]")) {
  let reset = 0;
  button.addEventListener("click", async () => {
    const text = button.dataset.copy ?? "";
    clearTimeout(reset);
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
      copyStatus.textContent = `Copied: ${text}`;
    } catch {
      // No clipboard access (an insecure origin, or a refused permission): select it, so ⌘C is one key away.
      const code = button.parentElement?.querySelector("code");
      if (code) getSelection()?.selectAllChildren(code);
      button.textContent = "Press ⌘C";
      copyStatus.textContent = "Couldn't copy. The command is selected, press Command C.";
    }
    reset = window.setTimeout(() => {
      button.textContent = "Copy";
    }, 1600);
  });
}

// MARK: Install tabs

const tabs = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')];

function selectTab(selected: HTMLButtonElement, moveFocus: boolean) {
  for (const tab of tabs) {
    const isSelected = tab === selected;
    tab.setAttribute("aria-selected", String(isSelected));
    tab.tabIndex = isSelected ? 0 : -1;
    $<HTMLElement>(`#${tab.getAttribute("aria-controls")}`).hidden = !isSelected;
  }
  if (moveFocus) selected.focus();
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTab(tab, false));
  tab.addEventListener("keydown", (event) => {
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1 + tabs.length,
      Home: 0,
      End: tabs.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    selectTab(tabs[moves[event.key] % tabs.length], true);
  });
});

mountDemo();
