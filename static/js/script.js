"use strict";

// This improves the forms in the browser. Flask repeats all validation because
// JavaScript can be disabled or a request can be sent without using the page.
const numberPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const calculatorForm = document.querySelector("#calculator-form");

function datasetTokens(text) {
  return text.trim().split(/[,\s]+/).filter(Boolean);
}

function validateDataset(text) {
  if (text.length > 200000) return "Use at most 200,000 characters in your dataset.";
  const tokens = datasetTokens(text);
  if (!tokens.length) return "Enter at least one number before calculating.";
  if (tokens.length > 10000) return "Use at most 10,000 numbers in one calculation.";
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (!numberPattern.test(token)) {
      const preview = token.length > 35 ? `${token.slice(0, 35)}…` : token;
      return `Value ${index + 1} ("${preview}") is not a valid number.`;
    }
    const value = Number(token);
    if (!Number.isFinite(value) || Math.abs(value) > 1e100) {
      return `Value ${index + 1} must be finite and between -1e100 and 1e100.`;
    }
  }
  return "";
}

if (calculatorForm) {
  const dataset = document.querySelector("#dataset");
  const error = document.querySelector("#dataset-error");
  const counter = document.querySelector("#value-count");
  const exampleButton = document.querySelector("#use-example");
  const clearButton = document.querySelector("#clear-dataset");
  // Controls that need JavaScript are only exposed when it has loaded.
  exampleButton.hidden = false;
  clearButton.hidden = false;

  function updateCounter() {
    const count = datasetTokens(dataset.value).length;
    counter.textContent = `${count.toLocaleString()} ${count === 1 ? "value" : "values"}`;
    error.hidden = true;
    error.textContent = "";
    dataset.removeAttribute("aria-invalid");
  }

  // Editing or clearing should not leave results that appear to match new input.
  function resetResults() {
    document.querySelectorAll("[data-result]").forEach((element) => {
      element.textContent = "—";
      element.classList.remove("stat-value-list");
      element.classList.add("empty-value");
    });
    document.querySelector(".result-status").textContent = "Ready when you are";
    document.querySelector(".saved-caption")?.remove();
    const sorted = document.querySelector("#sorted-values");
    const message = document.createElement("p");
    message.className = "empty-description";
    message.textContent = "An ordered view of your numbers will appear here.";
    sorted.replaceChildren(message);
    document.querySelector("#sorted-count").textContent = "Ascending order";
    document.querySelector("#result-footnote").textContent = "Enter a dataset and calculate to see all 10 statistics.";
  }

  dataset.addEventListener("input", () => { updateCounter(); resetResults(); });
  exampleButton.addEventListener("click", () => {
    dataset.value = "10, 15, 20, 20, 25, 30";
    updateCounter();
    resetResults();
    dataset.focus();
  });
  clearButton.addEventListener("click", () => {
    dataset.value = "";
    updateCounter();
    resetResults();
    dataset.focus();
  });
  calculatorForm.addEventListener("submit", (event) => {
    const message = validateDataset(dataset.value);
    if (message) {
      event.preventDefault();
      error.textContent = message; // Never insert dataset text as HTML.
      error.hidden = false;
      dataset.setAttribute("aria-invalid", "true");
      dataset.focus();
    }
  });
  updateCounter();
}

const registerForm = document.querySelector("#register-form");
if (registerForm) {
  const password = registerForm.querySelector("#password");
  const confirmation = registerForm.querySelector("#confirm_password");
  function checkPasswords() {
    confirmation.setCustomValidity(
      confirmation.value && confirmation.value !== password.value
        ? "Your passwords do not match."
        : ""
    );
  }
  password.addEventListener("input", checkPasswords);
  confirmation.addEventListener("input", checkPasswords);
}

// Clear-all has its own server-rendered confirmation page, even without JS.
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// SQLite stores UTC. Add the UTC suffix explicitly before local formatting.
document.querySelectorAll("time[data-local-time]").forEach((element) => {
  const raw = element.getAttribute("datetime");
  const timestamp = raw.includes("T") ? raw : `${raw.replace(" ", "T")}Z`;
  const date = new Date(timestamp);
  if (!Number.isNaN(date.getTime())) {
    element.textContent = new Intl.DateTimeFormat(undefined, {
      year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    }).format(date);
    element.title = `${raw} UTC`;
    element.setAttribute("datetime", date.toISOString());
  }
});

const timeZoneNote = document.querySelector("#time-zone-note");
if (timeZoneNote) timeZoneNote.textContent = "Times shown in your local time zone.";
