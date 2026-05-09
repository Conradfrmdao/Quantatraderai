import { useState } from "react";
import { Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform } from "react-native";
import { useSignUp } from "@clerk/clerk-expo";
import { useRouter, Link } from "expo-router";

export default function SignUpScreen() {
  const { signUp, setActive, isLoaded } = useSignUp();
  const router = useRouter();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [code,     setCode]     = useState("");
  const [step,     setStep]     = useState<"form" | "verify">("form");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const onSignUp = async () => {
    if (!isLoaded) return;
    setLoading(true); setError("");
    try {
      await signUp.create({ emailAddress: email, password });
      await signUp.prepareEmailAddressVerification({ strategy: "email_code" });
      setStep("verify");
    } catch (e: unknown) {
      setError((e as { errors?: { message: string }[] }).errors?.[0]?.message ?? "Sign up failed");
    } finally { setLoading(false); }
  };

  const onVerify = async () => {
    if (!isLoaded) return;
    setLoading(true); setError("");
    try {
      const res = await signUp.attemptEmailAddressVerification({ code });
      if (res.status === "complete") {
        await setActive({ session: res.createdSessionId });
        router.replace("/(app)/dashboard");
      }
    } catch (e: unknown) {
      setError((e as { errors?: { message: string }[] }).errors?.[0]?.message ?? "Invalid code");
    } finally { setLoading(false); }
  };

  if (step === "verify") return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.root}>
      <Text style={s.logo}>Check your email</Text>
      <Text style={s.sub}>We sent a 6-digit code to {email}</Text>
      <TextInput style={s.input} placeholder="Verification code" placeholderTextColor="#555"
        value={code} onChangeText={setCode} keyboardType="number-pad" />
      {error ? <Text style={s.error}>{error}</Text> : null}
      <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={onVerify} disabled={loading}>
        <Text style={s.btnTxt}>{loading ? "Verifying…" : "Verify email"}</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.root}>
      <Text style={s.logo}>QuantatraderAI</Text>
      <Text style={s.sub}>Create your account</Text>
      <TextInput style={s.input} placeholder="Email" placeholderTextColor="#555"
        value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
      <TextInput style={s.input} placeholder="Password" placeholderTextColor="#555"
        value={password} onChangeText={setPassword} secureTextEntry />
      {error ? <Text style={s.error}>{error}</Text> : null}
      <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={onSignUp} disabled={loading}>
        <Text style={s.btnTxt}>{loading ? "Creating account…" : "Create account"}</Text>
      </TouchableOpacity>
      <Link href="/(auth)/sign-in" asChild>
        <TouchableOpacity style={s.link}>
          <Text style={s.linkTxt}>Already have an account? <Text style={{ color: "#4ade80" }}>Sign in</Text></Text>
        </TouchableOpacity>
      </Link>
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
  link:       { marginTop: 20, alignItems: "center" },
  linkTxt:    { color: "#555", fontSize: 13 },
});
