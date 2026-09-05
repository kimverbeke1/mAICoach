from AICoach.chat.ai_message_handler import (
    handle_message
)


def main():

    print()
    print("=== MATCHFIT AI ===")
    print()

    while True:

        question = input(
            "\nVraag > "
        )

        if (
            question.lower()
            == "exit"
        ):
            break

        answer = handle_message(
            question
        )

        print()
        print(answer)
        print()


if __name__ == "__main__":
    main()