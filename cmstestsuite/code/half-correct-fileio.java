import java.util.Scanner;
import java.io.PrintWriter;
import java.io.File;
import java.io.FileNotFoundException;

public class Task {

    public static void main(String[] args) throws FileNotFoundException {
    	File file = new File("input.txt");
        Scanner scanner = new Scanner(file);
        int n = scanner.nextInt();
        PrintWriter writer = new PrintWriter("output.txt");
        writer.println("correct "+(n % 2 == 1 ? n : 0) );
        writer.close();
    }
}
