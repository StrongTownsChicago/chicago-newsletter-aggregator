// Client wiring for the /preferences rule modal: add, edit and onboarding
// states, the daily/weekly sections, the ward picker, and form validation.
import type { StarterRule } from "../lib/onboarding";
import { findRuleFormError } from "../lib/rule-form";

/** A saved rule, as its edit button's data attributes describe it. */
interface EditableRule {
  id: string;
  name: string;
  topics: string[];
  wardNumbers: string[];
  searchTerm: string;
  frequency: string;
  isActive: boolean;
}

function readEditableRule(dataset: DOMStringMap): EditableRule {
  return {
    id: dataset.ruleId || "",
    name: dataset.ruleName || "",
    topics: JSON.parse(dataset.ruleTopics || "[]") as string[],
    wardNumbers: JSON.parse(dataset.ruleWardNumbers || "[]") as string[],
    searchTerm: dataset.ruleSearchTerm || "",
    frequency: dataset.ruleDeliveryFrequency || "daily",
    isActive: dataset.ruleActive === "true",
  };
}

export function initRuleModal(): void {
  const modal = document.getElementById("ruleModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalSubtitle = document.getElementById("modalSubtitle");
  const defaultModalSubtitle = modalSubtitle?.textContent ?? "";
  const ruleForm = document.getElementById("ruleForm") as HTMLFormElement;
  const ruleIdInput = document.getElementById("ruleId") as HTMLInputElement;
  const ruleNameInput = document.getElementById("ruleName") as HTMLInputElement;
  const searchTermInput = document.getElementById("searchTerm") as HTMLInputElement;
  const isActiveInput = document.getElementById("isActive") as HTMLInputElement;
  const notificationTypeRadios = document.querySelectorAll<HTMLInputElement>('input[name="notification_type"]');
  const dailyOptionsSection = document.getElementById("dailyOptionsSection");
  const weeklyOptionsSection = document.getElementById("weeklyOptionsSection");
  const wardFilterSection = document.getElementById("wardFilterSection");
  const cancelBtn = document.getElementById("cancelBtn");
  const addRuleBtns = document.querySelectorAll("#addRuleBtn, #addRuleBtn2");
  const editRuleBtns = document.querySelectorAll(".edit-rule-btn");
  const toggleWardsBtn = document.getElementById("toggleWardsBtn");
  const wardSelectionContainer = document.getElementById("wardSelectionContainer");

  /** Show or hide the ward picker and label its toggle to match. */
  function setWardPickerExpanded(expanded: boolean): void {
    wardSelectionContainer?.classList.toggle("hidden", !expanded);
    if (toggleWardsBtn) toggleWardsBtn.textContent = expanded ? "Hide Wards" : "Show Wards";
  }

  // Toggle Ward Section
  toggleWardsBtn?.addEventListener("click", () => {
    setWardPickerExpanded(wardSelectionContainer?.classList.contains("hidden") ?? false);
  });

  /** The hidden delivery_frequency field, added to the form on first use. */
  function setDeliveryFrequency(frequency: "daily" | "weekly"): void {
    let frequencyInput = document.getElementById("hidden_frequency") as HTMLInputElement | null;
    if (!frequencyInput) {
      frequencyInput = document.createElement("input");
      frequencyInput.type = "hidden";
      frequencyInput.name = "delivery_frequency";
      frequencyInput.id = "hidden_frequency";
      ruleForm.appendChild(frequencyInput);
    }
    frequencyInput.value = frequency;
  }

  /** Check `to`'s topics that were checked in `from`, then clear `from` so topics aren't submitted twice. */
  function moveTopicSelection(from: NodeListOf<HTMLInputElement> | undefined, to: NodeListOf<HTMLInputElement> | undefined): void {
    const checkedTopics = Array.from(from ?? [])
      .filter((cb) => cb.checked)
      .map((cb) => cb.value);
    to?.forEach((cb) => {
      cb.checked = checkedTopics.includes(cb.value);
    });
    from?.forEach((cb) => (cb.checked = false));
  }

  /** Show the options for the frequency; the ward filter is daily-only. */
  function showSectionsFor(frequency: "daily" | "weekly"): void {
    const weekly = frequency === "weekly";
    dailyOptionsSection?.classList.toggle("hidden", weekly);
    weeklyOptionsSection?.classList.toggle("hidden", !weekly);
    wardFilterSection?.classList.toggle("hidden", weekly);
  }

  // Toggle sections based on notification type
  function toggleNotificationTypeSections(): void {
    const selectedType = document.querySelector<HTMLInputElement>('input[name="notification_type"]:checked');
    const frequency = selectedType?.value === "weekly" ? "weekly" : "daily";

    // Get topic checkboxes from both sections
    const dailyTopicCheckboxes = dailyOptionsSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]');
    const weeklyTopicCheckboxes = weeklyOptionsSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]');

    if (frequency === "weekly") {
      moveTopicSelection(dailyTopicCheckboxes, weeklyTopicCheckboxes);
      // Weekly summaries are citywide: clear ward selections
      document.querySelectorAll<HTMLInputElement>('input[name="wards"]').forEach((cb) => (cb.checked = false));
      setWardPickerExpanded(false);
    } else {
      moveTopicSelection(weeklyTopicCheckboxes, dailyTopicCheckboxes);
    }
    showSectionsFor(frequency);
    setDeliveryFrequency(frequency);
  }

  notificationTypeRadios.forEach((radio) => {
    radio.addEventListener("change", toggleNotificationTypeSections);
  });

  // Initialize on page load
  toggleNotificationTypeSections();

  // Open modal for a new rule, reset to the default (daily) state
  function openNewRuleModal(): void {
    modalTitle!.textContent = "Add Notification Rule";
    if (modalSubtitle) modalSubtitle.textContent = defaultModalSubtitle;
    ruleForm.action = "/api/notifications/create-rule";
    ruleForm.reset();
    ruleIdInput.value = "";
    searchTermInput.value = "";

    // Reset to default (daily)
    notificationTypeRadios[0].checked = true;

    // Reset wards UI
    setWardPickerExpanded(false);

    toggleNotificationTypeSections();
    modal?.classList.remove("hidden");
  }

  addRuleBtns.forEach((btn) => {
    btn?.addEventListener("click", openNewRuleModal);
  });

  // Onboarding: open the new-rule modal in its starter state
  function openStarterRuleModal(starterRule: StarterRule): void {
    openNewRuleModal();
    modalTitle!.textContent = "Create Your First Alert";
    if (modalSubtitle) {
      modalSubtitle.textContent = "You'll only receive emails once you save an alert. Pick the topics you care about.";
    }
    ruleNameInput.value = starterRule.name;

    notificationTypeRadios.forEach((radio) => {
      radio.checked = radio.value === starterRule.deliveryFrequency;
    });
    toggleNotificationTypeSections();
  }

  const starterRuleData = modal?.dataset.starterRule;
  if (starterRuleData) {
    openStarterRuleModal(JSON.parse(starterRuleData) as StarterRule);
  }

  /** Check the rule's wards, opening the picker when any is selected. */
  function selectWards(wardNumbers: string[]): void {
    let anySelected = false;
    ruleForm.querySelectorAll<HTMLInputElement>('input[name="wards"]').forEach((checkbox) => {
      checkbox.checked = wardNumbers.includes(checkbox.value);
      anySelected ||= checkbox.checked;
    });
    setWardPickerExpanded(anySelected);
  }

  // Open modal for editing rule
  function openEditRuleModal(rule: EditableRule): void {
    modalTitle!.textContent = "Edit Notification Rule";
    if (modalSubtitle) modalSubtitle.textContent = defaultModalSubtitle;
    ruleForm.action = "/api/notifications/update-rule";
    ruleIdInput.value = rule.id;
    ruleNameInput.value = rule.name;
    searchTermInput.value = rule.searchTerm;
    isActiveInput.checked = rule.isActive;

    // Set notification type based on frequency
    notificationTypeRadios.forEach((radio) => {
      if (radio.value === rule.frequency) radio.checked = true;
    });

    // Trigger toggle to show correct sections
    toggleNotificationTypeSections();

    // Check the appropriate topic checkboxes in the VISIBLE section only
    const visibleSection = rule.frequency === "weekly" ? weeklyOptionsSection : dailyOptionsSection;
    visibleSection?.querySelectorAll<HTMLInputElement>('input[name="topics"]').forEach((checkbox) => {
      checkbox.checked = rule.topics.includes(checkbox.value);
    });

    // Weekly rules have no wards (the picker is hidden)
    if (rule.frequency === "daily") {
      selectWards(rule.wardNumbers);
    }

    modal?.classList.remove("hidden");
  }

  editRuleBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      openEditRuleModal(readEditableRule((e.currentTarget as HTMLButtonElement).dataset));
    });
  });

  // Form validation before submission
  ruleForm?.addEventListener("submit", (e) => {
    const frequencyInput = document.getElementById("hidden_frequency") as HTMLInputElement | null;
    const errorMessage = findRuleFormError({
      frequency: frequencyInput?.value || "daily",
      searchTerm: searchTermInput.value.trim(),
      topicCount: ruleForm.querySelectorAll('input[name="topics"]:checked').length,
    });
    if (errorMessage) {
      e.preventDefault();
      alert(errorMessage);
    }
  });

  // Close modal
  cancelBtn?.addEventListener("click", () => {
    modal?.classList.add("hidden");
  });

  // Close on background click
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });
}
