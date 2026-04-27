async function search() {
  const q = document.getElementById("query").value;
  const resultsBox = document.getElementById("results");

  // update URL (no reload)
  const newUrl = `/search?q=${encodeURIComponent(q)}`;
  window.history.pushState({}, "", newUrl);

  resultsBox.innerHTML = "Searching...";

  try {
    const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();

    resultsBox.innerHTML = "";

    if (!data.length) {
      resultsBox.innerHTML = "<p>No results found</p>";
      return;
    }

    data.forEach(item => {
      const div = document.createElement("div");
      div.className = "result";

      div.innerHTML = `
        <a href="${item.url}" target="_blank">${item.title}</a>
        <div class="score">Score: ${item.score} (${item.status})</div>
      `;

      resultsBox.appendChild(div);
    });

  } catch (err) {
    resultsBox.innerHTML = "<p>Error fetching results</p>";
  }
}
