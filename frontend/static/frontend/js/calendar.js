(() => {
  "use strict";

  const LARGE_RESULT_THRESHOLD = 200;

  const showStatus = (statusElement, state, message) => {
    statusElement.hidden = false;
    statusElement.dataset.state = state;
    statusElement.textContent = message;
  };

  const showFailure = (workspace, statusElement) => {
    workspace.setAttribute("aria-busy", "false");
    showStatus(
      statusElement,
      "error",
      "Interactive calendar unavailable. Use the complete chronological list below."
    );
  };

  const endpointEvents = (payload) => {
    if (
      !payload ||
      payload.state !== "ready" ||
      !Array.isArray(payload.events) ||
      typeof payload.event_count !== "number"
    ) {
      throw new Error("Invalid calendar response");
    }

    return payload.events.map((event, contractOrder) => {
      if (!event || !event.calendar) {
        throw new Error("Invalid calendar event");
      }
      return {
        ...event.calendar,
        extendedProps: {
          ...event.calendar.extendedProps,
          contractOrder,
        },
      };
    });
  };

  const initializeCalendar = async (workspace) => {
    if (workspace.dataset.calendarEnabled !== "true") {
      return;
    }

    const statusElement = workspace.querySelector("[data-calendar-status]");
    const largeResultElement = workspace.querySelector(
      "[data-calendar-large-result]"
    );
    const viewport = workspace.querySelector("[data-calendar-viewport]");
    const canvas = workspace.querySelector("[data-calendar-canvas]");
    if (!statusElement || !largeResultElement || !viewport || !canvas) {
      return;
    }

    workspace.setAttribute("aria-busy", "true");
    showStatus(statusElement, "loading", "Loading interactive calendar…");

    if (!window.FullCalendar || !window.FullCalendar.Calendar) {
      showFailure(workspace, statusElement);
      return;
    }

    try {
      const response = await window.fetch(workspace.dataset.calendarEventsUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error("Calendar request failed");
      }

      const payload = await response.json();
      const events = endpointEvents(payload);
      workspace.setAttribute("aria-busy", "false");

      if (events.length === 0) {
        showStatus(
          statusElement,
          "empty",
          "No entries are available for this visual view. The list below confirms the empty result."
        );
        return;
      }

      const calendar = new window.FullCalendar.Calendar(canvas, {
        initialView:
          workspace.dataset.calendarView === "week"
            ? "dayGridWeek"
            : "dayGridMonth",
        initialDate: workspace.dataset.calendarStartDate,
        timeZone: workspace.dataset.calendarTimezone,
        headerToolbar: false,
        height: "auto",
        events,
        displayEventTime: false,
        editable: false,
        selectable: false,
        navLinks: false,
        eventStartEditable: false,
        eventDurationEditable: false,
        dayMaxEvents: true,
        eventOrder: "contractOrder",
        eventOrderStrict: true,
        eventDidMount(info) {
          const source = info.event.extendedProps.sourceLabel;
          const status = info.event.extendedProps.statusLabel;
          info.el.setAttribute(
            "aria-label",
            `${info.event.title}. ${source}. ${status}.`
          );
        },
      });
      // The viewport must be measurable before FullCalendar lays out;
      // rendering inside the hidden container collapses every day cell.
      viewport.hidden = false;
      try {
        calendar.render();
      } catch (_renderError) {
        viewport.hidden = true;
        throw _renderError;
      }
      showStatus(
        statusElement,
        "ready",
        `Interactive calendar ready with ${payload.event_count} entries. The complete list remains below.`
      );

      if (payload.event_count > LARGE_RESULT_THRESHOLD) {
        largeResultElement.hidden = false;
        largeResultElement.textContent =
          `This view contains ${payload.event_count} entries and may be crowded. ` +
          "Use the chronological list below for complete detail.";
      }
    } catch (_error) {
      showFailure(workspace, statusElement);
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    document
      .querySelectorAll("[data-calendar-workspace]")
      .forEach((workspace) => initializeCalendar(workspace));
  });
})();
