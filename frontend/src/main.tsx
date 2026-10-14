import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import Accuracy from "./pages/Accuracy";
import Alerts from "./pages/Alerts";
import Assistant from "./pages/Assistant";
import Dashboard from "./pages/Dashboard";
import Events from "./pages/Events";
import Forecast from "./pages/Forecast";
import Overrides from "./pages/Overrides";
import Scenarios from "./pages/Scenarios";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Dashboard /> },
      { path: "/forecast", element: <Forecast /> },
      { path: "/scenarios", element: <Scenarios /> },
      { path: "/accuracy", element: <Accuracy /> },
      { path: "/alerts", element: <Alerts /> },
      { path: "/events", element: <Events /> },
      { path: "/overrides", element: <Overrides /> },
      { path: "/assistant", element: <Assistant /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
