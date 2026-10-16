import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initRuleModal } from "../../client/rule-modal";

/** The ids and inputs the rule modal script relies on, as RuleList and RuleModal render them. */
function renderPage({ starterRule }: { starterRule?: string } = {}): void {
  document.body.innerHTML = `
    <button id="addRuleBtn">Add Rule</button>
    <button class="edit-rule-btn" data-rule-id="r1" data-rule-name="Weekly" data-rule-topics='["housing"]'
      data-rule-ward-numbers="[]" data-rule-search-term="" data-rule-delivery-frequency="weekly" data-rule-active="true">Edit</button>
    <button class="edit-rule-btn" data-rule-id="r2" data-rule-name="Daily" data-rule-topics="[]"
      data-rule-ward-numbers='["2"]' data-rule-search-term="bike lanes" data-rule-delivery-frequency="daily" data-rule-active="false">Edit</button>
    <div id="ruleModal" class="hidden">
      <h3 id="modalTitle">Add Notification Rule</h3>
      <p id="modalSubtitle">Configure when you want to receive email notifications</p>
      <form id="ruleForm" method="POST">
        <input type="hidden" id="ruleId" name="rule_id" />
        <input type="text" id="ruleName" name="name" />
        <input type="radio" name="notification_type" value="daily" checked />
        <input type="radio" name="notification_type" value="weekly" />
        <div id="dailyOptionsSection"><input type="text" id="searchTerm" name="search_term" /><input type="checkbox" name="topics" value="housing" /><input type="checkbox" name="topics" value="transportation" /></div>
        <div id="weeklyOptionsSection" class="hidden"><input type="checkbox" name="topics" value="housing" /><input type="checkbox" name="topics" value="transportation" /></div>
        <div id="wardFilterSection">
          <button type="button" id="toggleWardsBtn">Show Wards</button>
          <div id="wardSelectionContainer" class="hidden">
            <input type="checkbox" name="wards" value="2" /><input type="checkbox" name="wards" value="10" />
          </div>
        </div>
        <input type="checkbox" id="isActive" name="is_active" checked />
      </form>
      <button type="button" id="cancelBtn">Cancel</button>
    </div>`;
  if (starterRule) byId("ruleModal").dataset.starterRule = starterRule;
}

const byId = (id: string) => document.getElementById(id)!;
const isHidden = (id: string) => byId(id).classList.contains("hidden");
const input = (selector: string) => document.querySelector<HTMLInputElement>(selector)!;
const checkedValues = (selector: string) =>
  [...document.querySelectorAll<HTMLInputElement>(selector)].filter((box) => box.checked).map((box) => box.value);
const click = (element: Element) => element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
const frequency = () => input("#hidden_frequency").value;

function chooseType(value: "daily" | "weekly"): void {
  const radio = input(`input[name="notification_type"][value="${value}"]`);
  radio.checked = true;
  radio.dispatchEvent(new Event("change"));
}

function submitForm(): boolean {
  const event = new Event("submit", { cancelable: true });
  byId("ruleForm").dispatchEvent(event);
  return event.defaultPrevented;
}

describe("rule modal", () => {
  const alerts: string[] = [];

  beforeEach(() => {
    alerts.length = 0;
    vi.stubGlobal("alert", (message: string) => alerts.push(message));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts as a daily rule and opens empty for a new rule", () => {
    renderPage();
    initRuleModal();
    expect(frequency()).toBe("daily");
    expect(isHidden("ruleModal")).toBe(true);

    click(byId("addRuleBtn"));
    expect(isHidden("ruleModal")).toBe(false);
    expect(byId("modalTitle").textContent).toBe("Add Notification Rule");
    expect((byId("ruleForm") as HTMLFormElement).getAttribute("action")).toBe("/api/notifications/create-rule");
    expect(input("#ruleId").value).toBe("");
  });

  it("moves checked topics between the daily and weekly sections and hides wards for weekly", () => {
    renderPage();
    initRuleModal();
    input('#dailyOptionsSection input[value="housing"]').checked = true;
    input('input[name="wards"][value="2"]').checked = true;

    chooseType("weekly");
    expect(frequency()).toBe("weekly");
    expect(checkedValues('#weeklyOptionsSection input[name="topics"]')).toEqual(["housing"]);
    expect(checkedValues('#dailyOptionsSection input[name="topics"]')).toEqual([]);
    expect(checkedValues('input[name="wards"]')).toEqual([]);
    expect([isHidden("dailyOptionsSection"), isHidden("weeklyOptionsSection"), isHidden("wardFilterSection")]).toEqual([
      true,
      false,
      true,
    ]);

    chooseType("daily");
    expect(frequency()).toBe("daily");
    expect(checkedValues('#dailyOptionsSection input[name="topics"]')).toEqual(["housing"]);
    expect(checkedValues('#weeklyOptionsSection input[name="topics"]')).toEqual([]);
    expect(isHidden("wardFilterSection")).toBe(false);
  });

  it("toggles the ward picker", () => {
    renderPage();
    initRuleModal();
    click(byId("toggleWardsBtn"));
    expect([isHidden("wardSelectionContainer"), byId("toggleWardsBtn").textContent]).toEqual([false, "Hide Wards"]);
    click(byId("toggleWardsBtn"));
    expect([isHidden("wardSelectionContainer"), byId("toggleWardsBtn").textContent]).toEqual([true, "Show Wards"]);
  });

  it("fills the form from a weekly rule's edit button", () => {
    renderPage();
    initRuleModal();
    click(document.querySelectorAll(".edit-rule-btn")[0]);
    expect(byId("modalTitle").textContent).toBe("Edit Notification Rule");
    expect((byId("ruleForm") as HTMLFormElement).getAttribute("action")).toBe("/api/notifications/update-rule");
    expect([input("#ruleId").value, input("#ruleName").value, input("#isActive").checked]).toEqual(["r1", "Weekly", true]);
    expect(frequency()).toBe("weekly");
    expect(checkedValues('#weeklyOptionsSection input[name="topics"]')).toEqual(["housing"]);
    expect(submitForm()).toBe(false);
  });

  it("fills the form from a daily rule's edit button and opens its wards", () => {
    renderPage();
    initRuleModal();
    click(document.querySelectorAll(".edit-rule-btn")[1]);
    expect([input("#searchTerm").value, input("#isActive").checked]).toEqual(["bike lanes", false]);
    expect(frequency()).toBe("daily");
    expect(checkedValues('input[name="wards"]')).toEqual(["2"]);
    expect([isHidden("wardSelectionContainer"), byId("toggleWardsBtn").textContent]).toEqual([false, "Hide Wards"]);
    expect(submitForm()).toBe(false);
  });

  it("blocks saving a rule with nothing to match", () => {
    renderPage();
    initRuleModal();
    expect(submitForm()).toBe(true);
    chooseType("weekly");
    expect(submitForm()).toBe(true);
    expect(alerts).toEqual([
      "Please select at least one topic or enter a search phrase for daily digest.",
      "Please select at least one topic for weekly summaries.",
    ]);
  });

  it("opens in the onboarding state with the starter rule", () => {
    renderPage({ starterRule: JSON.stringify({ name: "Weekly Summary", deliveryFrequency: "weekly" }) });
    initRuleModal();
    expect(isHidden("ruleModal")).toBe(false);
    expect(byId("modalTitle").textContent).toBe("Create Your First Alert");
    expect(input("#ruleName").value).toBe("Weekly Summary");
    expect(frequency()).toBe("weekly");
  });

  it("closes on Cancel and on a click outside the dialog", () => {
    renderPage();
    initRuleModal();
    click(byId("addRuleBtn"));
    click(byId("cancelBtn"));
    expect(isHidden("ruleModal")).toBe(true);

    click(byId("addRuleBtn"));
    click(byId("modalTitle"));
    expect(isHidden("ruleModal")).toBe(false);
    click(byId("ruleModal"));
    expect(isHidden("ruleModal")).toBe(true);
  });
});
