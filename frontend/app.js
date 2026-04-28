async function search() {
  const q = document.getElementById("query").value;
  const resultsBox = document.getElementById("results");

  resultsBox.innerHTML = "Searching...";

  const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
  const data = await res.json();

  resultsBox.innerHTML = "";

  if (data.did_you_mean) {
    const hint = document.createElement("div");
    hint.className = "suggestion";
    hint.innerHTML = `Did you mean: <b>${data.did_you_mean}</b>`;
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

    div.innerHTML = `
      <a href="${item.url}" target="_blank">${item.title}</a>
      <div class="score">Score: ${item.score} (${item.status})</div>
    `;

    resultsBox.appendChild(div);
  });
}

window.onload = () => {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");

  if (q) {
    document.getElementById("query").value = q;
    search();
  }
};
