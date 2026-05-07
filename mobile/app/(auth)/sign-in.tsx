import { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform } from "react-native";
import { useSignIn } from "@clerk/clerk-expo";
import { useRouter } from "expo-router";

export default function SignInScreen() {
  const { signIn, setActive, isLoaded } = useSignIn();
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  const onSignIn = async () => {
    if (!isLoaded) return;
    setLoading(true);
    setError("");
    try {
      const res = await signIn.create({ identifier: email, password });
      if (res.status === "complete") {
        await setActive({ session: res.createdSessionId });
        router.replace("/(app)/dashboard");
      }
    } catch (e: unknown) {
      setError((e as { errors?: { message: string }[] }).errors?.[0]?.message ?? "Sign in failed");
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.root}>
      <Text style={s.logo}>QuantatraderAI</Text>
      <Text style={s.sub}>AI-powered trading platform</Text>
      <TextInput style={s.input} placeholder="Email" placeholderTextColor="#555" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
      <TextInput style={s.input} placeholder="Password" placeholderTextColor="#555" value={password} onChangeText={setPassword} secureTextEntry />
      {error ? <Text style={s.error}>{error}</Text> : null}
      <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={onSignIn} disabled={loading}>
        <Text style={s.btnTxt}>{loading ? "Signing in…" : "Sign in"}</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root:       { flex: 1, backgroundColor: "#000", padding: 28, justifyContent: "center" },
  logo:       { fontSize: 28, fontWeight: "700", color: "#fff", marginBottom: 6, textAlign: "center" },
  sub:        { fontSize: 13, color: "#555", marginBottom: 40, textAlign: "center" },
  input:      { backgroundColor: "#111", borderWidth: 1, borderColor: "#222", borderRadius: 12, padding: 14, fontSize: 15, color: "#fff", marginBottom: 14 },
  btn:        { backgroundColor: "#fff", borderRadius: 12, padding: 16, alignItems: "center", marginTop: 6 },
  btnDisabled:{ opacity: 0.5 },
  btnTxt:     { color: "#000", fontWeight: "700", fontSize: 15 },
  error:      { color: "#f87171", fontSize: 13, marginBottom: 10 },
});
