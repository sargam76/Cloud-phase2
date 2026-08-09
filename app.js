let currentPage = 1;
let chartInstances = {};
let totalPages = 1;

(async function init() {
  const user = await requireAuth();
  if (!user) return;

  document.getElementById("userName").textContent = user.name;
  document.getElementById("authProvider").textContent = user.provider === "github" ? "GitHub OAuth" : "Email/Password";

  await loadInsights();
  await loadRecipes();

  document.getElementById("dietSelect").addEventListener("change", function() {
    currentPage = 1;
    loadRecipes();
  });

  let searchTimer;
  document.getElementById("searchInput").addEventListener("input", function() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
      currentPage = 1;
      loadRecipes();
    }, 300);
  });

  document.getElementById("prevPageBtn").addEventListener("click", function() {
    if (currentPage > 1) { currentPage--; loadRecipes(); }
  });
  document.getElementById("nextPageBtn").addEventListener("click", function() {
    if (currentPage < totalPages) { currentPage++; loadRecipes(); }
  });
})();

async function loadInsights() {
  document.getElementById("apiStatus").textContent = "Loading nutritional insights...";
  const res = await fetch(API_BASE + "/nutritional-insights");
  if (!res.ok) {
    document.getElementById("metaLine").textContent = "No cached data yet.";
    document.getElementById("apiStatus").textContent = "Failed to load insights.";
    return;
  }
  const data = await res.json();
  document.getElementById("apiStatus").textContent = "Loaded from cache.";

  const meta = data.metadata || {};
  document.getElementById("metaLine").textContent =
    "Served from cache - computed in " + meta.execution_time_seconds + "s - " +
    meta.total_recipes_processed + " recipes - generated " + meta.generated_at_utc;

  const dietTypes = data.avg_macros.map(function(d) { return d.Diet_type; });
  const select = document.getElementById("dietSelect");
  while (select.options.length > 1) select.remove(1);
  dietTypes.forEach(function(dt) {
    const opt = document.createElement("option");
    opt.value = dt;
    opt.textContent = dt.charAt(0).toUpperCase() + dt.slice(1);
    select.appendChild(opt);
  });

  renderBarChart(data.avg_macros);
  renderScatterPlot(data.top_protein_recipes);
  renderHeatmap(data.avg_macros);
  renderPieChart(data.diet_recipe_counts);
}

function renderBarChart(avgMacros) {
  new Chart(document.getElementById("barChart"), {
    type: "bar",
    data: {
      labels: avgMacros.map(function(d) { return d.Diet_type; }),
      datasets: [
        { label: "Protein (g)", data: avgMacros.map(function(d) { return d["Protein(g)"]; }), backgroundColor: "#2563eb" },
        { label: "Carbs (g)", data: avgMacros.map(function(d) { return d["Carbs(g)"]; }), backgroundColor: "#16a34a" },
        { label: "Fat (g)", data: avgMacros.map(function(d) { return d["Fat(g)"]; }), backgroundColor: "#9333ea" }
      ]
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } }
  });
}

function renderScatterPlot(topProtein) {
  const groups = {};
  topProtein.forEach(function(r) {
    groups[r.diet_type] = groups[r.diet_type] || [];
    groups[r.diet_type].push(r);
  });
  const colors = ["#2563eb", "#dc2626", "#16a34a", "#f59e0b", "#9333ea"];
  const datasets = Object.keys(groups).map(function(diet, i) {
    return {
      label: diet,
      data: groups[diet].map(function(r, idx) { return { x: idx, y: r["Protein(g)"] }; }),
      backgroundColor: colors[i % colors.length]
    };
  });
  new Chart(document.getElementById("scatterPlot"), {
    type: "scatter",
    data: { datasets: datasets },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } }
  });
}

function renderHeatmap(avgMacros) {
  let html = '<table class="w-full"><thead><tr><th class="text-left">Diet</th><th>Protein</th><th>Carbs</th><th>Fat</th></tr></thead><tbody>';
  avgMacros.forEach(function(d) {
    html += "<tr><td class='pr-2'>" + d.Diet_type + "</td><td class='text-center bg-blue-100'>" + d["Protein(g)"] +
            "</td><td class='text-center bg-green-100'>" + d["Carbs(g)"] + "</td><td class='text-center bg-purple-100'>" + d["Fat(g)"] + "</td></tr>";
  });
  html += "</tbody></table>";
  document.getElementById("heatmap").innerHTML = html;
}

function renderPieChart(dietCounts) {
  new Chart(document.getElementById("pieChart"), {
    type: "pie",
    data: {
      labels: dietCounts.map(function(d) { return d.Diet_type; }),
      datasets: [{
        data: dietCounts.map(function(d) { return d.recipe_count; }),
        backgroundColor: ["#2563eb", "#dc2626", "#16a34a", "#f59e0b", "#9333ea"]
      }]
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } }
  });
}

async function loadRecipes() {
  const search = document.getElementById("searchInput").value.trim();
  const dietType = document.getElementById("dietSelect").value;
  const params = new URLSearchParams({ page: currentPage, page_size: 10, diet_type: dietType, search: search });

  document.getElementById("apiStatus").textContent = "Loading recipes...";
  const res = await fetch(API_BASE + "/recipes?" + params);
  if (!res.ok) { document.getElementById("apiStatus").textContent = "Failed to load recipes."; return; }
  const data = await res.json();
  document.getElementById("apiStatus").textContent = "Loaded recipes from cache.";

  totalPages = data.total_pages;
  currentPage = data.page;

  document.getElementById("recipeRows").innerHTML = data.results.map(function(r) {
    return "<tr class='border-t'><td class='p-2'>" + r.Recipe_name + "</td><td class='p-2 capitalize'>" + r.Diet_type +
           "</td><td class='p-2 capitalize'>" + r.Cuisine_type + "</td><td class='p-2'>" + r["Protein(g)"] + "</td></tr>";
  }).join("");

  document.getElementById("pageLabel").textContent = "Page " + data.page + " of " + data.total_pages + " (" + data.total_results + " results)";
}
