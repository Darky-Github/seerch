async function search() {
  const q = document.getElementById("query").value;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const resultsBox = document.getElementById("results");

  resultsBox.innerHTML = "<div class='meta'>Searching...</div>";

  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}&mode=${mode}`);
    const data = await res.json();

    resultsBox.innerHTML = "";

    if (!data.results || data.results.length === 0) {
      resultsBox.innerHTML = "<div class='meta'>No results found.</div>";
      return;
    }

    data.results.forEach(item => {
      const div = document.createElement("div");
      div.className = "result";

      div.innerHTML = `
        <a href="${item.url}" target="_blank">${item.title || item.url}</a>
        <div class="meta">${item.url} • Score: ${item.score}</div>
        <div class="snippet">${item.snippet}</div>
      `;

      resultsBox.appendChild(div);
    });

  } catch (err) {
    resultsBox.innerHTML = "<div class='meta'>Something went wrong.</div>";
  }
}

/* ENTER KEY SUPPORT */
document.getElementById("query").addEventListener("keypress", function (e) {
  if (e.key === "Enter") {
    search();
  }
});
