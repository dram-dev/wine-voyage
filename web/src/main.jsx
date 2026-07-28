import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import WineVoyage from "./WineVoyage.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <WineVoyage />
  </StrictMode>
);
