import GenorovaChatAppV11 from "./GenorovaChatAppV11";
import { AuthProvider } from "./auth";

export default function App() {
  return (
    <AuthProvider>
      <GenorovaChatAppV11 />
    </AuthProvider>
  );
}
