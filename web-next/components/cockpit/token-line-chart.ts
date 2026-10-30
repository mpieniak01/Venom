import {
  Chart, LineController, LineElement, PointElement, CategoryScale,
  LinearScale, Filler, Legend, Tooltip,
} from "chart.js";

// Only the line chart used by the token trend; no other controllers/scales.
Chart.register(LineController, LineElement, PointElement, CategoryScale, LinearScale, Filler, Legend, Tooltip);
export default Chart;
