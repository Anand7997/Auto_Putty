import com.aventstack.extentreports.ExtentReports;
import com.aventstack.extentreports.ExtentTest;
import com.aventstack.extentreports.Status;
import com.aventstack.extentreports.reporter.ExtentSparkReporter;
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class ExtentReportGenerator {
    private static final Gson GSON = new Gson();

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            throw new IllegalArgumentException("Usage: ExtentReportGenerator <input-json> <output-html>");
        }

        Path inputJson = Paths.get(args[0]);
        Path outputHtml = Paths.get(args[1]);
        Files.createDirectories(outputHtml.getParent());

        ReportPayload payload = readPayload(inputJson);

        ExtentSparkReporter spark = new ExtentSparkReporter(outputHtml.toString());
        String title = payload.context.getOrDefault("title", "Extent Report");
        spark.config().setDocumentTitle(title);
        spark.config().setReportName(title);

        ExtentReports extent = new ExtentReports();
        extent.attachReporter(spark);
        extent.setSystemInfo("Generated At", payload.generatedAt);
        extent.setSystemInfo("Execution Id", payload.context.getOrDefault("execution_id", "Latest Execution"));
        extent.setSystemInfo("Executor", payload.context.getOrDefault("executor_type", ""));
        extent.setSystemInfo("Browser", payload.context.getOrDefault("browser_name", ""));

        for (Map<String, Object> result : payload.results) {
            String testName = stringValue(result.get("testcase_name"), stringValue(result.get("testCase"), "Unknown Test"));
            String suiteType = stringValue(result.get("suite_type"), "general");
            String statusRaw = stringValue(result.get("status"), "UNKNOWN").toUpperCase();

            ExtentTest test = extent.createTest(testName);
            test.assignCategory(suiteType);

            String author = stringValue(result.get("username"), "");
            if (!author.isBlank()) {
                test.assignAuthor(author);
            }

            String browser = stringValue(result.get("browser_name"), stringValue(result.get("browser_info"), ""));
            if (!browser.isBlank()) {
                test.assignDevice(browser);
            }

            test.info("Executor: " + stringValue(result.get("executor_type"), "selenium"));
            test.info("Duration: " + stringValue(result.get("execution_time"), ""));

            List<Map<String, Object>> stepResults = asMapList(result.get("step_results"));
            if (!stepResults.isEmpty()) {
                for (int i = 0; i < stepResults.size(); i++) {
                    Map<String, Object> step = stepResults.get(i);
                    Status stepStatus = mapStatus(stringValue(step.get("status"), "INFO"));
                    String stepText = stringValue(
                        step.get("message"),
                        stringValue(
                            step.get("step_description"),
                            stringValue(step.get("description"), "Step " + (i + 1))
                        )
                    );
                    test.log(stepStatus, stepText);
                }
            } else {
                test.log(mapStatus(statusRaw), "Execution completed with status: " + statusRaw);
            }

            String error = stringValue(result.get("error_message"), stringValue(result.get("error"), ""));
            if (!error.isBlank()) {
                test.fail(error);
            } else if (mapStatus(statusRaw) == Status.PASS) {
                test.pass("Execution passed");
            } else if (mapStatus(statusRaw) == Status.SKIP) {
                test.skip("Execution skipped");
            } else if (mapStatus(statusRaw) != Status.INFO) {
                test.log(mapStatus(statusRaw), "Execution finished with status: " + statusRaw);
            }
        }

        extent.flush();
    }

    private static ReportPayload readPayload(Path inputJson) throws IOException {
        try (Reader reader = Files.newBufferedReader(inputJson, StandardCharsets.UTF_8)) {
            Type payloadType = new TypeToken<ReportPayload>() {}.getType();
            ReportPayload payload = GSON.fromJson(reader, payloadType);
            if (payload == null) {
                payload = new ReportPayload();
            }
            if (payload.context == null) {
                payload.context = Collections.emptyMap();
            }
            if (payload.results == null) {
                payload.results = Collections.emptyList();
            }
            if (payload.generatedAt == null) {
                payload.generatedAt = "";
            }
            return payload;
        }
    }

    private static Status mapStatus(String status) {
        String normalized = status == null ? "" : status.trim().toUpperCase();
        return switch (normalized) {
            case "PASS", "PASSED", "SUCCESS" -> Status.PASS;
            case "FAIL", "FAILED", "ERROR" -> Status.FAIL;
            case "SKIP", "SKIPPED" -> Status.SKIP;
            case "WARNING" -> Status.WARNING;
            default -> Status.INFO;
        };
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> asMapList(Object value) {
        if (value instanceof List<?>) {
            return (List<Map<String, Object>>) value;
        }
        return Collections.emptyList();
    }

    private static String stringValue(Object value, String fallback) {
        if (value == null) {
            return fallback;
        }
        String text = String.valueOf(value).trim();
        return text.isEmpty() ? fallback : text;
    }

    private static class ReportPayload {
        String generatedAt;
        Map<String, String> context;
        List<Map<String, Object>> results;
    }
}
