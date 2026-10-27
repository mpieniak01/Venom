import "./component-test-setup";
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SelectMenu } from "../components/ui/select-menu";

const originalRect = HTMLElement.prototype.getBoundingClientRect;
const originalHeight = Object.getOwnPropertyDescriptor(window, "innerHeight");
let triggerTop = 100;
let menuHeight = 100;

beforeEach(() => {
  triggerTop = 100;
  menuHeight = 100;
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 720 });
  HTMLElement.prototype.getBoundingClientRect = function () {
    if (this.classList.contains("test-select-trigger")) {
      return { top: triggerTop, bottom: triggerTop + 34, left: 100, right: 250, width: 150, height: 34, x: 100, y: triggerTop, toJSON() {} };
    }
    if (this.getAttribute("data-testid") === "test-select-menu") {
      return { top: 0, bottom: menuHeight, left: 0, right: 150, width: 150, height: menuHeight, x: 0, y: 0, toJSON() {} };
    }
    return originalRect.call(this);
  };
});

afterEach(() => {
  cleanup();
  HTMLElement.prototype.getBoundingClientRect = originalRect;
  if (originalHeight) Object.defineProperty(window, "innerHeight", originalHeight);
});

function renderSelect(onChange: (value: string) => void = () => {}) {
  return render(<SelectMenu
    value="normal"
    options={[
      { value: "direct", label: "Direct" },
      { value: "normal", label: "Normal" },
      { value: "disabled", label: "Disabled", disabled: true },
      { value: "complex", label: "Complex" },
    ]}
    onChange={onChange}
    className="test-select-trigger"
    buttonTestId="test-select-button"
    menuTestId="test-select-menu"
    optionTestIdPrefix="test-option"
  />);
}

describe("SelectMenu viewport and keyboard behavior", () => {
  it("opens below when there is room and above near the bottom; updates on scroll and resize", () => {
    renderSelect();
    fireEvent.click(screen.getByTestId("test-select-button"), { detail: 1 });
    const menu = screen.getByTestId("test-select-menu");
    assert.equal(menu.style.top, "142px");
    assert.equal(menu.style.maxHeight, "calc(100vh - 16px)");
    assert.equal(menu.style.overflowY, "auto");
    triggerTop = 686;
    fireEvent.scroll(window);
    assert.equal(menu.style.top, "578px");
    triggerTop = 200;
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 250 });
    fireEvent.resize(window);
    assert.equal(menu.style.top, "92px");
    menuHeight = 500;
    fireEvent.resize(window);
    assert.equal(menu.style.top, "8px");
  });

  it("places content-width menus above the lower edge and focuses the first enabled option when none is selected", () => {
    triggerTop = 686;
    render(<SelectMenu
      value="unknown"
      options={[{ value: "first", label: "First" }]}
      onChange={() => {}}
      className="test-select-trigger"
      menuWidth="content"
      buttonTestId="test-select-button"
      menuTestId="test-select-menu"
      optionTestIdPrefix="test-option"
    />);
    fireEvent.keyDown(screen.getByTestId("test-select-button"), { key: "ArrowDown" });
    const menu = screen.getByTestId("test-select-menu");
    assert.equal(menu.style.top, "578px");
    assert.equal(menu.style.width, "max-content");
    assert.equal(menu.style.overflowY, "auto");
    assert.equal(document.activeElement, screen.getByTestId("test-option-first"));
  });
  it("supports keyboard focus, arrow navigation, selection and Escape", () => {
    let selected = "";
    renderSelect((value) => { selected = value; });
    const trigger = screen.getByTestId("test-select-button");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = screen.getByRole("listbox");
    assert.equal(document.activeElement, screen.getByTestId("test-option-normal"));
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    assert.equal(document.activeElement, screen.getByTestId("test-option-complex"));
    fireEvent.keyDown(menu, { key: "Home" });
    assert.equal(document.activeElement, screen.getByTestId("test-option-direct"));
    fireEvent.keyDown(menu, { key: "End" });
    assert.equal(document.activeElement, screen.getByTestId("test-option-complex"));
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    assert.equal(document.activeElement, screen.getByTestId("test-option-normal"));
    fireEvent.click(screen.getByTestId("test-option-direct"), { detail: 0 });
    assert.equal(selected, "direct");
    assert.equal(document.activeElement, trigger);
    assert.equal(screen.queryByRole("listbox"), null);
    fireEvent.click(trigger, { detail: 0 });
    assert.equal(document.activeElement, screen.getByTestId("test-option-normal"));
    fireEvent.keyDown(window, { key: "Escape" });
    assert.equal(screen.queryByRole("listbox"), null);
    assert.equal(document.activeElement, trigger);
  });
});
