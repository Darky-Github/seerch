async function search() {
  const q = document.getElementById("query").value.trim();
  const resultsBox = document.getElementById("results");

  if (!q) return;

  window.history.pushState({}, "", `/search?q=${encodeURIComponent(q)}`);

  resultsBox.innerHTML = "Searching...";

  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    resultsBox.innerHTML = "";

    // Did you mean
    if (data.did_you_mean) {
      const hint = document.createElement("div");
      hint.className = "suggestion";

      hint.innerHTML = `Did you mean: <b>${data.did_you_mean}</b>`;

      hint.onclick = () => {
        document.getElementById("query").value = data.did_you_mean;
        search();
      };

      resultsBox.appendChild(hint);
    }

    const results = data.results || [];

    if (!results.length) {
      resultsBox.innerHTML = "<p>No results found</p>";
      return;
    }

    results.forEach(item => {
      const div = document.createElement("div");
      div.className = "result";

      const trustClass = item.trust === "Verified" ? "verified" : "normal";

      div.innerHTML = `
        <a href="${item.url}" target="_blank">${item.title}</a>
        <div class="meta">
          ${item.url}<br>
          Score: ${item.score}
          <span class="badge ${trustClass}">${item.trust}</span>
        </div>
        <div class="snippet">
          ${item.snippet || ""}
        </div>
      `;

      resultsBox.appendChild(div);
    });

  } catch (err) {
    resultsBox.innerHTML = "<p>Error fetching results</p>";
  }
}

// Enter key support
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("query");

  input.addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
      search();
    }
  });

  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");

  if (q) {
    input.value = q;
    search();
  }
});
